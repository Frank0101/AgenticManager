"""Edits the research ledger's tables, findings, text and links by ID, and reads it back.

The commands and their arguments are in SKILL.md and `--help`.

Why a script: the ledger is long, and a patch has to match text exactly once, so
every new row, finding, status change or move cost a hand-built edit. IDs and
ordering are mechanical, so they are the script's; what goes in the cells and the
findings is the agent's judgment. The reading commands (show, find, status) exist
so the agent never opens the whole ledger to check what it already holds, and they
print plain text, which costs fewer tokens than JSON. Every other command prints
one line of JSON.

Rows of a table with no ID (file coverage) append and are removed by matching
their Source cell.
"""
import argparse
import json
import os
import re
import sys

from common import (AREAS, COMPONENT_HEADER, DECISION_HEADER, FILE_HEADER, FINDING_FIELDS, FINDING_OPTIONAL, FOLDER_NAME,
                    GROUPS,
                    GAP_HEADER, LEDGER, QUEUE_HEADER, SOURCE_HEADER, investigation_dir, write_output_file)

# table name: (heading it sits under, default header, ID letters, or None when
# rows have no ID and append)
TABLES = {
    "queue-ready": ("### Ready / in progress", QUEUE_HEADER, "Q"),
    "queue-blocked": ("### Blocked", QUEUE_HEADER, "Q"),
    "queue-completed": ("### Completed", QUEUE_HEADER, "Q"),
    "sources": ("## Revisions and source register", SOURCE_HEADER, "S"),
    "file-coverage": ("### File reading coverage", FILE_HEADER, None),
    "decisions": ("## Open decisions", DECISION_HEADER, "D"),
    "gaps": ("## Evidence gaps", GAP_HEADER, "G"),
    "components": ("## Component inventory and evolution", COMPONENT_HEADER, "C"),
}
QUEUE_TABLES = ["queue-ready", "queue-blocked", "queue-completed"]
PLACEHOLDERS = {"None yet.", "None."}
LINKS_HEADING = "## Links"
FINDINGS_HEADING = "## Findings and validation chains"
TEXT_SECTIONS = ["Resume here", "Boundary, method and access", "Reflection"]
FINDING_START = re.compile(r"^### (F\d+) ", re.M)


def cells_of(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def render(cells):
    return "| " + " | ".join(cells) + " |"


def natural(row):
    match = re.match(r"([A-Za-z]+)(\d+)", row[0])
    return (match[1], int(match[2])) if match else (row[0], 0)


def section(lines, heading):
    """(index of the heading, index of the next heading or the end)."""
    start = next((i for i, line in enumerate(lines)
                 if line.strip() == heading), None)
    if start is None:
        raise SystemExit(f"the ledger has no {heading!r} section")
    end = next((i for i in range(start + 1, len(lines))
               if lines[i].startswith("#")), len(lines))
    return start, end


def table_span(lines, heading):
    """(start, end) of the first table under `heading`, or None."""
    start, end = section(lines, heading)
    first = next((i for i in range(start + 1, end)
                 if lines[i].startswith("|")), None)
    if first is None:
        return None
    last = first
    while last < end and lines[last].startswith("|"):
        last += 1
    return first, last


def drop_placeholder(lines, after, end):
    """Remove the first non-blank line in lines[after:end] if it is a placeholder."""
    for i in range(after, end):
        if lines[i].strip():
            if lines[i].strip() in PLACEHOLDERS:
                del lines[i]
            return


def rows_of(lines, span):
    return [cells_of(line) for line in lines[span[0] + 2:span[1]]]


def write_rows(lines, name, rows, header=None):
    """Put `rows` in the table `name`, creating it under its heading if there is none."""
    heading, default, _ = TABLES[name]
    span = table_span(lines, heading)
    if span is None:
        start, end = section(lines, heading)
        drop_placeholder(lines, start + 1, end)
        block = ["", render(header or default), render(
            ["---"] * len(header or default))]
        block += [render(r) for r in rows] + [""]
        lines[start + 1:start + 1] = block
        return
    head = lines[span[0]:span[0] + 2]
    lines[span[0]:span[1]] = head + [render(r) for r in rows]
    table_end = span[0] + 2 + len(rows)
    _, end = section(lines, heading)
    if rows:
        drop_placeholder(lines, table_end, end)
    elif not any(line.strip() in PLACEHOLDERS for line in lines[table_end:end]):
        lines[table_end:table_end] = ["", "None."]


def header_of(lines, name):
    span = table_span(lines, TABLES[name][0])
    return cells_of(lines[span[0]]) if span else TABLES[name][1]


def check_areas(name, header, cells):
    """The Areas cell of a source or a gap names evidence areas, comma separated."""
    if header[-1] != "Areas" or not cells:
        return
    wrong = [a for a in (x.strip()
                         for x in cells[-1].split(",")) if a and a not in AREAS]
    if wrong:
        raise SystemExit(f"{name} Areas must be some of: " +
                         ", ".join(AREAS) + "; not " + ", ".join(wrong))


def set_row(lines, name, row_id, cells):
    header = header_of(lines, name)
    row = ([row_id] if row_id else []) + list(cells)
    if len(row) != len(header):
        raise SystemExit(f"{name} has {len(header)} columns ({' | '.join(header)}), counting the ID if it has one; "
                         f"got {len(row)}")
    check_areas(name, header, row)
    span = table_span(lines, TABLES[name][0])
    rows = rows_of(lines, span) if span else []
    if row_id:
        rows = [r for r in rows if r[0] != row_id] + [row]
        rows.sort(key=natural)
    else:
        rows.append(row)
    write_rows(lines, name, rows, header)


def find_row(lines, row_id):
    for name in QUEUE_TABLES:
        span = table_span(lines, TABLES[name][0])
        for row in rows_of(lines, span) if span else []:
            if row[0] == row_id:
                return name, row
    raise SystemExit(f"no queue row {row_id}")


def move_row(lines, row_id, target, sets):
    source, row = find_row(lines, row_id)
    header = header_of(lines, source)
    for assignment in sets:
        column, _, value = assignment.partition("=")
        names = [h.casefold() for h in header]
        if column.casefold() not in names:
            raise SystemExit(
                f"no column {column!r}; the queue's are: " + " | ".join(header))
        row[names.index(column.casefold())] = value
    span = table_span(lines, TABLES[source][0])
    write_rows(lines, source, [r for r in rows_of(
        lines, span) if r[0] != row_id], header)
    set_row(lines, target, row[0], row[1:])


def next_id(text, kind):
    if kind == "F":
        found = re.findall(r"^### F(\d+) ", text, re.M)
    else:
        found = re.findall(rf"^\|\s*{kind}(\d+)\s*\|", text, re.M)
    width = max([2] + [len(n) for n in found])
    return f"{kind}{max([0] + [int(n) for n in found]) + 1:0{width}d}"


def set_link(lines, key, url):
    if LINKS_HEADING not in [line.strip() for line in lines]:
        lines += ["", LINKS_HEADING, "", "None yet."]
    start, end = section(lines, LINKS_HEADING)
    definitions = {}
    for line in lines[start + 1:end]:
        match = re.match(r"^\[([^\]]+)\]:\s*(\S+)", line)
        if match:
            definitions[match[1]] = match[2]
    definitions[key] = url
    body = ["", *(f"[{k}]: {v}" for k, v in sorted(definitions.items(),
                  key=lambda kv: kv[0].casefold())), ""]
    lines[start + 1:end] = body


def h2_end(lines, start):
    """Index of the next ## heading after `start`, or the end."""
    return next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))


def number(ident):
    return int(re.sub(r"\D", "", ident) or 0)


def findings_of(lines):
    """({ID: block text}, start, end) of the findings section."""
    start, _ = section(lines, FINDINGS_HEADING)
    end = h2_end(lines, start)
    body = "\n".join(lines[start + 1:end])
    parts = re.split(r"(?m)^(?=### F\d+ )", body)
    blocks = {}
    for part in parts:
        found = FINDING_START.match(part)
        if found:
            blocks[found[1]] = part.strip("\n")
    return blocks, start, end


def write_findings(lines, blocks, start, end):
    body = "\n\n".join(blocks[k] for k in sorted(
        blocks, key=number)) if blocks else "None yet."
    lines[start + 1:end] = ["", *body.split("\n"), ""]


def finding_block(ident, fields):
    wanted = ["title", *FINDING_FIELDS]
    missing = [f for f in wanted if not isinstance(
        fields.get(f), str) or not fields[f].strip()]
    extra = [f for f in fields if f not in wanted + FINDING_OPTIONAL]
    if missing or extra:
        raise SystemExit("a finding needs these fields, each text: " + ", ".join(wanted)
                         + "; it may also have " + ", ".join(FINDING_OPTIONAL)
                         + (f"; missing {', '.join(missing)}" if missing else "")
                         + (f"; unknown {', '.join(extra)}" if extra else ""))
    clean = {k: " ".join(v.split()) for k, v in fields.items()}
    return "\n".join([f"### {ident} — {clean['title']}", "",
                      *(f"- **{f}:** {clean[f]}" for f in FINDING_FIELDS + FINDING_OPTIONAL if f in clean)])


def set_finding(lines, ident, fields):
    blocks, start, end = findings_of(lines)
    blocks[ident] = finding_block(ident, fields)
    write_findings(lines, blocks, start, end)


def remove_finding(lines, ident):
    blocks, start, end = findings_of(lines)
    if ident not in blocks:
        raise SystemExit(f"no finding {ident}")
    del blocks[ident]
    write_findings(lines, blocks, start, end)


def remove_row(lines, name, row_id, match):
    heading, _, letters = TABLES[name]
    span = table_span(lines, heading)
    rows = rows_of(lines, span) if span else []
    if row_id:
        kept = [r for r in rows if r[0] != row_id]
    else:
        kept = [r for r in rows if match not in r[0]]
    if len(kept) == len(rows):
        raise SystemExit(f"no {name} row " +
                         (row_id or f"whose Source contains {match!r}"))
    if not row_id and len(rows) - len(kept) > 1:
        raise SystemExit(
            f"{match!r} matches {len(rows) - len(kept)} rows; use more of the text")
    write_rows(lines, name, kept, header_of(lines, name))


def remove_link(lines, key):
    start, end = section(lines, LINKS_HEADING)
    kept = [line for line in lines[start + 1:end]
            if not re.match(rf"^\[{re.escape(key)}\]:", line)]
    if len(kept) == len(lines[start + 1:end]):
        raise SystemExit(f"no link {key!r}")
    if not any(line.startswith("[") for line in kept):
        kept = ["", "None yet.", ""]
    lines[start + 1:end] = kept


def sync_sources(lines):
    """Write each source row's `Findings: ...` from the Evidence lines of the findings."""
    blocks, _, _ = findings_of(lines)
    cited = {}
    for ident, block in blocks.items():
        evidence = re.search(r"- \*\*Evidence:\*\*(.*)", block)
        for source in set(re.findall(r"\bS(\d+)\b", evidence[1] if evidence else "")):
            cited.setdefault(int(source), []).append(ident)
    heading = TABLES["sources"][0]
    span = table_span(lines, heading)
    rows = rows_of(lines, span) if span else []
    for row in rows:
        row[4] = re.sub(r"\s*Findings: [^.]*\.$", "", row[4])
        if number(row[0]) in cited:
            found = sorted(cited[number(row[0])], key=number)
            row[4] = f"{row[4].rstrip()} Findings: {', '.join(found)}.".strip()
    write_rows(lines, "sources", rows, header_of(lines, "sources"))


def set_text(lines, name, text):
    if name not in TEXT_SECTIONS:
        raise SystemExit("--section is one of: " + ", ".join(TEXT_SECTIONS))
    start, _ = section(lines, f"## {name}")
    end = h2_end(lines, start)
    lines[start + 1:end] = ["", *text.strip().split("\n"), ""]


def table_markdown(lines, name):
    span = table_span(lines, TABLES[name][0])
    return lines[span[0]:span[1]] if span else []


def show(lines, ident, name):
    if name == "findings":
        blocks, _, _ = findings_of(lines)
        return "\n".join(b.splitlines()[0].removeprefix("### ") for _, b in
                         sorted(blocks.items(), key=lambda kv: number(kv[0]))) or "No findings."
    if name:
        return "\n".join(table_markdown(lines, name)) or "None."
    blocks, _, _ = findings_of(lines)
    if re.fullmatch(r"F\d+", ident):
        if ident not in blocks:
            raise SystemExit(f"no finding {ident}")
        return blocks[ident]
    for table in TABLES:
        if TABLES[table][2] is None:
            continue
        span = table_span(lines, TABLES[table][0])
        for row in rows_of(lines, span) if span else []:
            if row[0].casefold() == ident.casefold():
                return "\n".join([f"{table} {row[0]}"] + [f"{h}: {c}" for h, c in
                                                          zip(header_of(lines, table)[1:], row[1:])])
    raise SystemExit(f"no record {ident}")


def snippet(text, needle, width=110):
    at = text.casefold().find(needle)
    start = max(0, at - 30)
    return ("..." if start else "") + text[start:start + width].replace("\n", " ")


def find(lines, text):
    needle = text.casefold()
    hits = []
    for table, (_, _, letters) in TABLES.items():
        span = table_span(lines, TABLES[table][0])
        for row in rows_of(lines, span) if span else []:
            cells = " | ".join(row)
            if needle in cells.casefold():
                hits.append(f"{table} {row[0]}: {snippet(cells, needle)}")
    blocks, _, _ = findings_of(lines)
    for ident, block in sorted(blocks.items(), key=lambda kv: number(kv[0])):
        if needle in block.casefold():
            line = next(line for line in block.splitlines()
                        if needle in line.casefold())
            hits.append(f"finding {ident}: {snippet(line, needle)}")
    start, end = section(lines, LINKS_HEADING)
    for line in lines[start + 1:end]:
        if line.startswith("[") and needle in line.casefold():
            hits.append(f"link {line}")
    if not hits:
        return f"no match for {text!r}"
    shown = hits[:40]
    return "\n".join(shown + ([f"... and {len(hits) - 40} more"] if len(hits) > 40 else []))


def coverage(lines):
    """Lines counting, per evidence area, the sources of each group and the gaps."""
    span = table_span(lines, TABLES["sources"][0])
    sources = rows_of(lines, span) if span else []
    span = table_span(lines, TABLES["gaps"][0])
    gaps = rows_of(lines, span) if span else []
    tally = {a: {g: 0 for g in GROUPS} for a in AREAS}
    untagged = []
    for row in sources:
        group = next(
            (g for g in GROUPS if row[1].casefold().startswith(g)), None)
        tagged = [a.strip() for a in row[-1].split(",") if a.strip() in AREAS]
        if group and not tagged:
            untagged.append(row[0])
        for area in tagged:
            if group:
                tally[area][group] += 1
    out = ["coverage (sources per area: " + " / ".join(GROUPS) + "; gaps):"]
    for area in AREAS:
        open_gaps = sum(area in [x.strip()
                        for x in g[-1].split(",")] for g in gaps)
        counts = " / ".join(str(tally[area][g]) for g in GROUPS)
        thin = [g for g in GROUPS if not tally[area][g]]
        out.append(f"  {area}: {counts}, {open_gaps} gaps" +
                   (f"  (none from {', '.join(thin)})" if thin else ""))
    if untagged:
        out.append("  sources with no Areas: " + ", ".join(untagged))
    return out


def status(lines):
    out = []
    counts = {}
    for table in QUEUE_TABLES:
        span = table_span(lines, TABLES[table][0])
        counts[table] = rows_of(lines, span) if span else []
    out.append(
        "queue: " + ", ".join(f"{len(counts[t])} {t.split('-')[1]}" for t in QUEUE_TABLES))
    for label, table in (("ready", "queue-ready"), ("blocked", "queue-blocked")):
        for row in counts[table]:
            out.append(f"  {label} {row[0]} [{row[5]}] {row[2][:100]}")
    blocks, _, _ = findings_of(lines)
    totals = [("findings", len(blocks))]
    for table in ("sources", "file-coverage", "components", "decisions", "gaps"):
        span = table_span(lines, TABLES[table][0])
        totals.append((table, len(rows_of(lines, span)) if span else 0))
    out.append("counts: " + ", ".join(f"{n} {name}" for name, n in totals))
    out += coverage(lines)
    unstarted = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            body = [x for x in lines[i + 1:h2_end(lines, i)] if x.strip()]
            if body in (["None yet."], []):
                unstarted.append(line[3:])
    out.append("not started: " +
               (", ".join(unstarted) if unstarted else "none"))
    return "\n".join(out)


def load(relative):
    path, _, _ = investigation_dir(relative)
    try:
        with open(os.path.join(path, LEDGER), encoding="utf-8") as f:
            return f.read()
    except OSError:
        raise SystemExit(
            f"{relative} has no {LEDGER}: run init_investigation.py first")


def save(relative, lines):
    text = "\n".join(lines).rstrip("\n") + "\n"
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{LEDGER}", text.encode("utf-8"))
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Edit the research ledger's tables, findings, text and links by ID.")
    commands = parser.add_subparsers(dest="command", required=True)
    names = ("next-id", "row", "move", "remove", "finding",
             "link", "unlink", "sync-sources", "text", "show", "find", "status")
    for name in names:
        sub = commands.add_parser(name)
        sub.add_argument("--investigation", required=True,
                         help="<Topic>_<YY-MM-DD>")
        if name == "next-id":
            sub.add_argument("--kind", required=True, choices=list("SQFCDG"))
        if name in ("row", "remove"):
            sub.add_argument("--table", required=True, choices=list(TABLES) +
                             (["findings"] if name == "remove" else []))
            sub.add_argument(
                "--id", help="the row's ID; leave out for file-coverage")
        if name == "remove":
            sub.add_argument(
                "--match", help="for file-coverage: text its Source cell contains")
        if name == "finding":
            sub.add_argument(
                "--id", help="the finding to replace; leave out to add the next one")
        if name == "move":
            sub.add_argument("--id", required=True)
            sub.add_argument("--to", required=True,
                             choices=["ready", "blocked", "completed"])
            sub.add_argument("--set", action="append",
                             default=[], help='"Column=value"')
        if name in ("link", "unlink"):
            sub.add_argument("--key", required=True)
        if name == "link":
            sub.add_argument("--url", required=True)
        if name == "show":
            sub.add_argument(
                "--id", help="a finding, or a row's ID")
            sub.add_argument("--table", choices=list(TABLES) + ["findings"])
        if name == "find":
            sub.add_argument("--text", required=True)
        if name == "text":
            sub.add_argument("--section", required=True,
                             help=" or ".join(TEXT_SECTIONS))
    args = parser.parse_args(argv)
    text = load(args.investigation)
    lines = text.split("\n")
    result = {}
    if args.command in ("show", "find", "status"):
        if args.command == "show" and bool(args.id) == bool(args.table):
            raise SystemExit("show takes --id or --table")
        print({"show": lambda: show(lines, args.id, args.table), "find": lambda: find(lines, args.text),
               "status": lambda: status(lines)}[args.command]())
        return
    if args.command == "next-id":
        print(json.dumps({"id": next_id(text, args.kind)}))
        return
    if args.command == "row":
        _, _, letters = TABLES[args.table]
        if bool(letters) != bool(args.id):
            raise SystemExit(
                f"{args.table} " + ("needs --id" if letters else "has no IDs: leave --id out"))
        if args.id and args.id[0] not in letters:
            raise SystemExit(
                f"{args.table} IDs start with {' or '.join(letters)}")
        cells = json.load(sys.stdin)
        if not isinstance(cells, list) or not all(isinstance(c, str) for c in cells):
            raise SystemExit(
                "standard input must be a JSON list of strings, the row's cells")
        set_row(lines, args.table, args.id, [
                c.replace("\n", " ") for c in cells])
    elif args.command == "move":
        move_row(lines, args.id, f"queue-{args.to}", args.set)
    elif args.command == "remove":
        if args.table == "findings":
            if not args.id:
                raise SystemExit("findings need --id")
            remove_finding(lines, args.id)
        else:
            _, _, letters = TABLES[args.table]
            if bool(letters) == bool(args.match) or (letters and not args.id):
                raise SystemExit(
                    f"{args.table} " + ("takes --id" if letters else "has no IDs: use --match"))
            remove_row(lines, args.table, args.id, args.match)
    elif args.command == "finding":
        fields = json.load(sys.stdin)
        if not isinstance(fields, dict):
            raise SystemExit(
                "standard input must be a JSON object, the finding's title and fields")
        ident = args.id or next_id(text, "F")
        if not re.fullmatch(r"F\d+", ident):
            raise SystemExit("--id is F and its number, such as F07")
        set_finding(lines, ident, fields)
        result["id"] = ident
    elif args.command == "link":
        if not re.fullmatch(r"[A-Za-z0-9._-]+", args.key) or not re.match(r"https?://", args.url):
            raise SystemExit(
                "--key is letters, digits, dots, hyphens and underscores; --url starts with http(s)://")
        set_link(lines, args.key, args.url)
    elif args.command == "unlink":
        remove_link(lines, args.key)
    elif args.command == "sync-sources":
        sync_sources(lines)
    elif args.command == "text":
        set_text(lines, args.section, sys.stdin.read())
    else:
        raise SystemExit(f"unknown command {args.command}")
    print(json.dumps({"path": save(args.investigation, lines), **result}))


if __name__ == "__main__":
    main()
