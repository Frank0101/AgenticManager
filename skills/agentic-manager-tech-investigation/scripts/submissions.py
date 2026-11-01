"""Checks a task's submission and writes everything it implies to the ledger.

The agent never writes an ID, a table or a question's state: a submission cites
every record in double brackets, a new one by a key ([[f1]]) and one the ledger
holds by its ID ([[F07]]), and the script assigns the IDs, moves the queue and
keeps the ledger in step. A submission is written whole or not at all: it is
applied to a copy, every problem is collected by field, and the ledger changes
only when there is none.
"""
import re

from common import (DESIGN_ORDER, COVERAGE, LEFT_OUT, OUTSIDE_SCOPE, SCOPE_ANSWERS, SCOPE_QUESTION, USER_DECIDED, citation,
                    cited_evidence_problem, claim_length_problem, ids, read_in_part, recorded_ids)
from ledger import (TABLES, as_written, input_columns, basis, duplicate_of, finish_write, find_row,
                    header_of, move_row, next_id, put_row, refuse_cited, search_reference, set_design_basis,
                    table_rows, write_rows, record_review)

# A submission's fields for each kind of record, in the order of the ledger's
# columns after the ID: the script writes the cells from them.
FIELDS = {
    "sources": ["kind", "reference", "revision", "coverage", "superseded_by"],
    "findings": ["claim", "sources", "limits"],
    "gaps": ["gap", "missing", "would_close", "blocked_by", "owner_and_next_check", "evidence"],
    "decisions": ["decision", "position", "candidates_and_constraints", "owner_and_next_check", "evidence"],
    "boundaries": ["name", "kind", "within", "evidence"],
    "identities": ["name", "kind", "reaches", "in_the_target", "evidence"],
    "components": ["name", "kind", "boundary", "responsibility", "code", "state", "in_the_target", "evidence"],
    "connections": ["from", "to", "how", "data", "waits_for_reply", "identity", "state", "in_the_target",
                    "evidence"],
    "flows": ["entry_point", "connections", "in_the_target", "evidence"],
}
# Fields a submission may leave out, with the value written then.
DEFAULTS = {"superseded_by": "None"}
# A key names a record new in this submission: its table's letter, in lower
# case, and a number, so it can't be taken for an ID. It is cited as [[s1]],
# which stands out in any field, so every citation of one is found and replaced,
# and none is left in the ledger pointing nowhere.
KEY_REFERENCE = re.compile(r"\[\[([A-Za-z]\d+)\]\]")
# A word shaped like an ID, but not part of an address such as s3://bucket, a
# dotted name such as s3.amazonaws.com or a hyphenated one such as kb-s3.
BARE_REFERENCE = re.compile(r"(?<![-./\w])\b[A-Za-z]\d+\b(?![-:/]|\.\w)")
RECORD_ID = re.compile(r"[A-Z]\d{2,}")
# The fields that only cite other records, where the name of a record written
# bare, not as [[s1]], is refused: it would be left as prose, its citation
# lost. Any other word shaped like an ID, such as V2, is prose.
CITING = {"sources": ["superseded_by"], "findings": ["sources"], "gaps": ["evidence"], "decisions": ["evidence"],
          "boundaries": ["within", "evidence"],
          "identities": ["reaches", "evidence"], "components": ["evidence", "boundary"],
          "connections": ["from", "to", "identity", "evidence"], "flows": ["connections", "evidence"],
          "questions": ["raised_by", "depends_on"]}
QUESTION_FIELDS = ["raised_by", "question", "depends_on"]
# The lines part of a Coverage as coverage_text() writes it.
COVERAGE_LINES = re.compile(r"lines (\d+-\d+(?:, \d+-\d+)*)(?: of (\d+))?")


def submit_scope(lines, data, asked):
    """Write the user's decision on each scope question of `asked`, the IDs
    handed out, as a scope boundary, close each with it, and add the research
    questions an included one opens; returns {key: ID}."""
    problems = Problems(lines)
    problems.only(data, ["decisions", "new_questions"])
    decisions = problems.items(data, "decisions")
    questions = problems.items(data, "new_questions", required=False)
    allocator = Allocator(lines)
    keys = {}
    for number, item in enumerate(questions):
        allocator.claim(keys, "questions", item,
                        f"new_questions[{number}]", problems)
    written = []
    decided = set()
    for number, item in enumerate(decisions):
        where = f"decisions[{number}]"
        problems.only(item, ["question", "topic", "answer"], where)
        question = referenced(item.get("question"))
        if question not in asked:
            problems.add(f"{where}.question is one of the questions handed out: "
                         + ", ".join(f"[[{ident}]]" for ident in asked))
            continue
        if question in decided:
            problems.add(f"{where}.question [[{question}]] is decided twice")
            continue
        decided.add(question)
        topic = problems.text(item, "topic", where)
        answer = problems.text(item, "answer", where)
        if answer and answer not in SCOPE_ANSWERS:
            problems.add(
                f"{where}.answer is one of: {', '.join(SCOPE_ANSWERS)}")
            continue
        if topic and answer:
            boundary = allocator.next("U")
            written += problems.put(lines, "scope", boundary,
                                    [topic, answer, citation(question)], where, keys)
            problems.guard(where, lambda q=question, b=boundary: move_row(
                lines, q, "queue-completed", {"Findings": f"{USER_DECIDED}{citation(b)}"}))
    written += add_questions(lines, questions, keys, problems)
    problems.stop()
    problems.guard("the decisions", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


def submit_research(lines, question, data):
    """Write an answer to `question`: its sources, findings and new questions,
    then close it, as answered, outside the scope or blocked; returns
    {key: ID}."""
    problems = Problems(lines)
    problems.only(data, ["sources", "findings", "new_questions", "outcome"])
    allocator = Allocator(lines)
    written = []
    sources = problems.items(data, "sources", required=False)
    findings = problems.items(data, "findings", required=False)
    questions = problems.items(data, "new_questions", required=False)
    outcome = data.get("outcome") if isinstance(data, dict) else None
    # Every key first, so records can cite each other in any order.
    keys = {}
    claim_reading(lines, sources, findings, keys, allocator, problems)
    for number, item in enumerate(questions):
        allocator.claim(keys, "questions", item,
                        f"new_questions[{number}]", problems)
    written += write_reading(lines, sources, findings, keys, problems)
    written += add_questions(lines, questions, keys, problems)
    written += close(lines, question, outcome, keys, allocator, problems)
    problems.stop()
    problems.guard("the answer", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


def claim_reading(lines, sources, findings, keys, allocator, problems):
    """Give the sources and findings of a submission their IDs in `keys`: a
    source read again keeps its ID, and what was read this time is added to
    its coverage, which only ever grows."""
    for number, item in enumerate(sources):
        allocator.claim(keys, "sources", item,
                        f"sources[{number}]", problems, same=read_before(lines, item))
    for number, item in enumerate(findings):
        allocator.claim(keys, "findings", item,
                        f"findings[{number}]", problems)


def write_reading(lines, sources, findings, keys, problems):
    """Write a submission's sources and findings, checked as research's are;
    returns the values written."""
    written = []
    for number, item in enumerate(sources):
        where = f"sources[{number}]"
        cells = problems.cells(item, "sources", where, keys, extra=["key"])
        if cells is not None and isinstance(cells[1], dict):
            cells[1] = problems.guard(
                where, lambda c=cells: search_reference(c[1]))
        if cells is not None:
            # A source read again keeps what the ledger holds of it: its
            # coverage grows, and it stays superseded unless the answer says
            # otherwise.
            held = {row[0]: row for row in table_rows(
                lines, "sources")}.get(read_before(lines, item) or "")
            cells[3] = problems.guard(f"{where}.coverage", lambda c=cells, h=held: coverage_text(
                c[3] if h is None else grown_coverage(coverage_fields(h[4]), c[3])))
            if held is not None and "superseded_by" not in item:
                cells[4] = held[6]
        if cells is not None and cells[1] is not None and cells[3] is not None:
            written += problems.put(lines, "sources",
                                    keys.get(key_of(item)), cells, where, keys)
    for number, item in enumerate(findings):
        where = f"findings[{number}]"
        cells = problems.cells(item, "findings", where,
                               keys, extra=["key", "partial"])
        if cells is None:
            continue
        cells[2] = partial_limits(lines, item, cells, where, problems, keys)
        if too_long := claim_length_problem(where, cells[0]):
            problems.add(too_long)
        written += problems.put(lines, "findings",
                                keys.get(key_of(item)), cells, where, keys)
    return written


def submit_design(lines, data):
    """Replace the system design with the one submitted, keeping the IDs given
    as keys and assigning new ones, with the sources and findings of what was
    read again to build it, then add its new questions and record what it was
    built from; returns {key: ID}."""
    problems = Problems(lines)
    problems.only(data, ["sources", "findings",
                  *DESIGN_ORDER, "new_questions"])
    allocator = Allocator(lines)
    before = {table: {row[0] for row in table_rows(
        lines, table)} for table in DESIGN_ORDER}
    items = {table: problems.items(data, table, required=False)
             for table in DESIGN_ORDER}
    questions = problems.items(data, "new_questions", required=False)
    sources = problems.items(data, "sources", required=False)
    findings = problems.items(data, "findings", required=False)
    keys = {}
    claim_reading(lines, sources, findings, keys, allocator, problems)
    for table in DESIGN_ORDER:
        for number, item in enumerate(items[table]):
            allocator.claim(keys, table, item,
                            f"{table}[{number}]", problems, keep=before[table])
    for number, item in enumerate(questions):
        allocator.claim(keys, "questions", item,
                        f"new_questions[{number}]", problems)
    for table in DESIGN_ORDER:
        write_rows(lines, table, [], header_of(lines, table))
    written = write_reading(lines, sources, findings, keys, problems)
    for table in DESIGN_ORDER:
        for number, item in enumerate(items[table]):
            where = f"{table}[{number}]"
            cells = problems.cells(item, table, where, keys, extra=["key"])
            if cells is not None:
                written += problems.put(lines, table,
                                        keys.get(key_of(item)), cells, where, keys)
    written += add_questions(lines, questions, keys, problems)
    kept = set(keys.values())
    for table in DESIGN_ORDER:
        for ident in sorted(before[table] - kept):
            problems.guard(f"{table} {ident}, left out",
                           lambda i=ident: refuse_cited(lines, i))
    problems.stop()
    # Recorded after its own findings are in, so a design never looks out of
    # date for what it read itself.
    set_design_basis(lines, basis(lines))
    problems.guard("the design", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


def submit_review(lines, data, round_number):
    """Record review round `round_number`: the questions it raised, added to
    the queue, or the user's choice to stop; returns {key: ID}."""
    problems = Problems(lines)
    if isinstance(data, dict) and "stopped" in data:
        problems.only(data, ["stopped"])
        stopped = problems.text(data, "stopped")
        problems.stop()
        record_review(lines, stopped=stopped)
        return {"ids": {}}
    problems.only(data, ["raised"])
    raised = problems.items(data, "raised", required=False)
    allocator = Allocator(lines)
    keys = {}
    for number, item in enumerate(raised):
        allocator.claim(keys, "questions", item, f"raised[{number}]", problems)
    for item in raised:
        if isinstance(item, dict):
            item.setdefault("raised_by", f"Review round {round_number}")
    written = add_questions(lines, raised, keys, problems, where="raised")
    problems.stop()
    record_review(lines, list(keys.values()))
    problems.guard("the review", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


def coverage_text(given):
    """A source's Coverage as the ledger writes it, from the submitted object:
    {"read": ..., "lines": [[1, 80]], "of": 352, "sections": [...], "files":
    [...], "note": ...}, as COVERAGE describes; exits on a malformed object.
    Whether a partial read names enough is coverage_problem()'s, checked when
    the row is written."""
    shape = ('coverage is an object such as {"read": "partial", "lines": [[1, 80], [200, 240]], "of": 352}; read is '
             f'one of: {", ".join(COVERAGE)}, and lines, of, sections, files and note are optional')
    if not isinstance(given, dict) or given.get("read") not in COVERAGE \
            or set(given) - {"read", "lines", "of", "sections", "files", "note"}:
        raise SystemExit(shape)
    size = given.get("of")
    if size is not None and (not isinstance(size, int) or size < 1):
        raise SystemExit("of is the number of lines the file has")
    spans = given.get("lines", [])
    if not isinstance(spans, list) or not all(
            isinstance(span, list) and len(span) == 2 and all(
                isinstance(n, int) for n in span)
            and 1 <= span[0] <= span[1] <= (size or span[1]) for span in spans):
        raise SystemExit(
            "lines lists the ranges read, as [[first, last]], within the file's lines")
    named = {name: given.get(name, []) for name in ("sections", "files")}
    for name, items in named.items():
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            raise SystemExit(f"{name} lists the {name} read, as texts")
    note = given.get("note", "")
    if not isinstance(note, str):
        raise SystemExit("note is a text")
    parts = []
    if spans:
        parts.append(
            "lines " + ", ".join(f"{a}-{b}" for a, b in spans) + (f" of {size}" if size else ""))
    parts += [f"{name}: {', '.join(items)}" for name,
              items in named.items() if items]
    parts += [note.strip()] if note.strip() else []
    return given["read"] + (": " + "; ".join(parts) if parts else "")


def grown_coverage(before, now):
    """The coverage of a source read again: `before`, as the ledger holds it,
    and `now`, what this read covers, together. The fuller read wins, as full
    covers everything; the lines, sections and files read are merged, lines
    covering a whole file making it full, and the notes kept. Exits on a `now`
    coverage_text() refuses."""
    coverage_text(now)
    read = min(before["read"], now["read"], key=COVERAGE.index)
    notes = list(dict.fromkeys(n for n in (
        before.get("note"), now.get("note")) if n))
    grown = {"read": read, **({"note": "; ".join(notes)} if notes else {})}
    if read == "full":
        return grown
    spans = sorted(before.get("lines", []) + now.get("lines", []))
    merged = []
    for first, last in spans:
        if merged and first <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], last)
        else:
            merged.append([first, last])
    size = now.get("of") or before.get("of")
    # Reads that together cover a file's every line read it in full.
    if size and merged == [[1, size]]:
        return {**grown, "read": "full"}
    if merged:
        grown["lines"] = merged
    if size:
        grown["of"] = size
    for name in ("sections", "files"):
        if items := list(dict.fromkeys(before.get(name, []) + now.get(name, []))):
            grown[name] = items
    return grown


def coverage_fields(text):
    """The fields of a Coverage coverage_text() wrote, so a source read again
    can add to it: its read, then each part it named."""
    read, _, rest = text.partition(": ")
    fields, notes = {"read": read.strip()}, []
    for part in rest.split("; ") if rest else []:
        if match := COVERAGE_LINES.fullmatch(part):
            fields["lines"] = [[int(n) for n in span.split("-")]
                               for span in match[1].split(", ")]
            if match[2]:
                fields["of"] = int(match[2])
        elif part.startswith(("sections: ", "files: ")):
            name, _, items = part.partition(": ")
            fields[name] = items.split(", ")
        else:
            notes.append(part)
    if notes:
        fields["note"] = "; ".join(notes)
    return fields


def read_before(lines, item):
    """The ID of the source the ledger already holds for the submitted source
    `item`, the same reference at the same revision, or None."""
    reference, revision = item.get("reference"), item.get("revision")
    if isinstance(reference, dict):
        try:
            reference = search_reference(reference)
        except SystemExit:
            return None
    if not isinstance(reference, str) or not isinstance(revision, str):
        return None
    return duplicate_of(lines, [None, "", reference, revision, "", "None", "None"])


def key_of(item):
    """The key a record `item` declares, without its brackets: a new one, such
    as f1, or the ID of a row it keeps, such as C03."""
    return referenced(item.get("key") if isinstance(item, dict) else None)


def referenced(text):
    """The ID or key `text` cites as [[F07]] or [[f1]], when that is all it holds, or None."""
    found = KEY_REFERENCE.fullmatch(
        text.strip()) if isinstance(text, str) else None
    return found[1] if found else None


def written_keys(keys):
    """{key as the agent writes it: ID} of a submission's records."""
    return {f"[[{key}]]": ident for key, ident in keys.items()}


def partial_limits(lines, item, cells, where, problems, keys):
    """The finding's Limits cell: its limits, then, for each source it cites
    read only in part, why the unread part can't change this claim. The
    submission gives the reasons by source, so the script asks for exactly
    one for each such source, and a reason given for another claim can't
    stand in for it; it sits in Limits, where a reader of the finding looks."""
    partly = {row[0]
              for row in table_rows(lines, "sources") if read_in_part(row)}
    cited = [ident for ident in dict.fromkeys(
        ids(cells[1], "S")) if ident in partly]
    given = item.get("partial", {})
    if not isinstance(given, dict):
        problems.add(
            f'{where}.partial is an object, such as {{"[[s1]]": "the unread lines are admin routes"}}')
        return cells[2]
    reasons = {}
    for written, reason in given.items():
        match = KEY_REFERENCE.fullmatch(written.strip())
        ident = keys.get(match[1], match[1]) if match else None
        if ident not in cited:
            problems.add(
                f"{where}.partial: {written} isn't a source this finding cites that was read only in part")
        elif not isinstance(reason, str) or not reason.strip():
            problems.add(f"{where}.partial.{written} needs text")
        else:
            reasons[ident] = problems.cite(
                reason, f"{where}.partial", keys, citing=False).strip().rstrip(".")
    if missing := [ident for ident in cited if ident not in reasons]:
        named = {ident: f"[[{key}]]" for key, ident in keys.items() if ident}
        sources = ", ".join(
            named.get(ident) or f"[[{ident}]]" for ident in missing)
        problems.add(f"{where}: cites {sources}, read only in part: read the rest, or say in partial, for "
                     f"{sources}, why the unread part can't change this claim")
    notes = [
        f"{citation(ident)} read in part: {reasons[ident]}." for ident in cited if ident in reasons]
    limits = "" if notes and cells[2] == "None" else cells[2]
    return " ".join([limits, *notes]).strip()


def add_questions(lines, questions, keys, problems, where="new_questions"):
    """Write each new question as a ready one, one with "for": "user" as a
    scope question; returns the values written."""
    written = []
    for number, item in enumerate(questions):
        at = f"{where}[{number}]"
        cells = problems.cells(item, "questions", at,
                               keys, extra=["key", "for"])
        if cells is not None and item.get("for", "user") != "user":
            problems.add(
                f'{at}.for is "user", for a scope question, or left out')
        elif cells is not None:
            if item.get("for") == "user":
                cells[1] = SCOPE_QUESTION + cells[1]
            written += problems.put(lines, "queue-ready",
                                    keys.get(key_of(item)), [*cells, ""], at, keys)
    return written


def close(lines, question, outcome, keys, allocator, problems):
    """Close `question` as `outcome` says: answered, with the findings that
    answer it and any other question the same reading answered; outside the
    scope a boundary leaves out; or blocked by a gap or decision, new or held;
    returns the values written."""
    if not isinstance(outcome, dict) or len(set(outcome) & {"answered", "blocked", "outside_scope"}) != 1:
        problems.add('outcome is {"answered": "[[f1]], [[F07]]"}, {"blocked": ...}: a gap {"gap": {...}}, a '
                     'decision {"decision": {...}}, or one the ledger holds, "[[G02]]", or {"outside_scope": "[[U01]]"}, the '
                     'scope boundary that leaves it out')
        return []
    if "outside_scope" in outcome:
        return close_outside_scope(lines, question, outcome, problems)
    if "answered" in outcome:
        problems.only(outcome, ["answered", "also_answers"], "outcome")
        answered = problems.cite(outcome.get(
            "answered"), "outcome.answered", keys)
        others = outcome.get("also_answers", {})
        if not isinstance(others, dict):
            problems.add('outcome.also_answers is {"[[Q05]]": "[[f2]]"}: each other question the reading answered, '
                         "with its findings")
            others = {}
        problems.guard("outcome", lambda: move_row(
            lines, question, "queue-completed", {"Findings": answered}))
        values = [answered]
        for written, findings in others.items():
            where = f"outcome.also_answers.{written}"
            other = referenced(written)
            if not other:
                problems.add(f"{where}: write the question as [[Q05]]")
                continue
            cited = problems.cite(findings, where, keys)
            found = problems.guard(where, lambda o=other: find_row(lines, o))
            if found is None:
                continue
            if found[0] not in ("queue-ready", "queue-in-progress"):
                problems.add(f"{where}: only an open question can be closed")
                continue
            problems.guard(where, lambda o=other, c=cited: move_row(
                lines, o, "queue-completed", {"Findings": c}))
            values.append(cited)
        return values
    problems.only(outcome, ["blocked"], "outcome")
    blocked = outcome["blocked"]
    if isinstance(blocked, str):
        held = {row[0] for table in ("gaps", "decisions")
                for row in table_rows(lines, table)}
        ident = referenced(blocked)
        if ident not in held:
            problems.add(
                f"outcome.blocked: {blocked} is no gap or decision the ledger holds, written as [[G02]]")
            return []
        values = [citation(ident)]
    elif isinstance(blocked, dict) and len(blocked) == 1 and next(iter(blocked)) in ("gap", "decision"):
        kind = next(iter(blocked))
        table = kind + "s"
        ident = allocator.next(table[0].upper())
        cells = problems.cells(
            blocked[kind], table, f"outcome.blocked.{kind}", keys)
        evidence = TABLES[table][1].index("Evidence") - 1
        if cells and (traced := cited_evidence_problem(f"outcome.blocked.{kind}", cells[evidence])):
            problems.add(traced)
        values = problems.put(lines, table, ident, cells,
                              f"outcome.blocked.{kind}", keys) if cells else []
    else:
        problems.add(
            'outcome.blocked is {"gap": {...}}, {"decision": {...}} or one the ledger holds, as [[G02]]')
        return []
    problems.guard("outcome", lambda: move_row(lines, question,
                   "queue-blocked", {"Depends on": citation(ident)}))
    return values


def close_outside_scope(lines, question, outcome, problems):
    """Close `question` as outside the scope a boundary the user decided
    leaves out, citing it; returns the values written."""
    problems.only(outcome, ["outside_scope"], "outcome")
    given = outcome["outside_scope"]
    boundary = referenced(given) if isinstance(given, str) else None
    row = {row[0]: row for row in table_rows(
        lines, "scope")}.get(boundary or "")
    if row is None or row[2] not in LEFT_OUT:
        problems.add(f"outcome.outside_scope: {given} is no scope boundary decided as mention only or exclude, "
                     "written as [[U01]]")
        return []
    cited = citation(boundary)
    problems.guard("outcome", lambda: move_row(lines, question, "queue-completed",
                                               {"Findings": f"{OUTSIDE_SCOPE}{cited}"}))
    return [cited]


class Allocator:
    """The IDs a submission's new records get: each the next free one of its
    letter, counted from the ledger as it was, so a row left out of a
    rewritten design never gives its ID to another."""

    def __init__(self, lines):
        self.text = "\n".join(lines)
        self.taken = {}

    def next(self, letter):
        """The next free ID of `letter`."""
        number = self.taken.get(letter) or int(next_id(self.text, letter)[1:])
        self.taken[letter] = number + 1
        return f"{letter}{number:02d}"

    def claim(self, keys, table, item, where, problems, keep=(), same=None):
        """Give the record `item` of `table` its ID in `keys`: [[C03]], a row
        of `keep` the ledger holds, stays; a new key, [[c1]], gets `same`, the
        ID of the row it updates, or else the next one."""
        letter = "Q" if table == "questions" else TABLES[table][2]
        key = key_of(item)
        if key in keep:
            keys[key] = key
        elif not (key and re.fullmatch(rf"{letter.lower()}\d+", key)):
            kept = f", or the ID of a row it keeps, such as [[{letter}03]]" if keep else ""
            problems.add(f"{where}.key is [[{letter.lower()}1]]: {letter.lower()} and a number in double "
                         f"brackets{kept}")
        elif key in keys:
            problems.add(f"{where}.key [[{key}]] is used twice")
        else:
            keys[key] = same or self.next(letter)


class Problems:
    """What is wrong with a submission, by field: collected, not raised, so
    one answer lists them all."""

    def __init__(self, lines):
        self.found = []
        self.held = recorded_ids("\n".join(lines))

    def add(self, problem):
        """Record a problem."""
        self.found.append(problem)

    def stop(self):
        """Exit with every problem found, if any: nothing is written then."""
        if self.found:
            raise SystemExit("nothing was written; fix each of these and submit again:\n- "
                             + "\n- ".join(dict.fromkeys(self.found)))

    def guard(self, where, action):
        """The result of `action`, or None, recording its exit as a problem
        at `where`."""
        try:
            return action()
        except SystemExit as error:
            self.add(f"{where}: {error.code}")
            return None

    def only(self, data, allowed, where="the submission"):
        """Record the fields of `data` no field of the submission has."""
        if not isinstance(data, dict):
            self.add(f"{where} is a JSON object")
            return
        if extra := sorted(set(data) - set(allowed)):
            self.add(
                f"{where} has no field {', '.join(extra)}; its fields are: {', '.join(allowed)}")

    def items(self, data, name, required=True):
        """The list `data[name]` of objects; [] after recording what is wrong."""
        value = data.get(name) if isinstance(data, dict) else None
        if value is None and not required:
            return []
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            self.add(f"{name} is a list of objects")
            return []
        return value

    def text(self, data, name, where="the submission"):
        """The text `data[name]`; "" after recording that it is missing."""
        value = data.get(name) if isinstance(data, dict) else None
        if not isinstance(value, str) or not value.strip():
            self.add(f"{where}.{name} needs text" if where !=
                     "the submission" else f"{name} needs text")
            return ""
        return value.strip()

    def cells(self, item, table, where, keys, extra=()):
        """The cells of a record of `table` from its fields, keys replaced by
        IDs in the fields that cite; None after recording what is wrong."""
        names = QUESTION_FIELDS if table == "questions" else FIELDS[table]
        if not isinstance(item, dict):
            self.add(
                f"{where} is an object with the fields: {', '.join(names)}")
            return None
        self.only(item, [*extra, *names], where)
        cells = []
        for name in names:
            value = item.get(name, DEFAULTS.get(name))
            if name in ("reference", "coverage") and isinstance(value, dict):
                cells.append(value)
                continue
            if not isinstance(value, str) or not value.strip():
                self.add(f"{where}.{name} needs text")
                value = ""
            value = self.cite(value, f"{where}.{name}",
                              keys, name in CITING.get(table, ()))
            cells.append(value.strip())
        return cells

    def cite(self, value, where, keys, citing=True):
        """`value` with each [[F07]] or [[f1]] written as the citation of its
        record, recording a key no record of the submission has, a key of the
        submission written bare, which no reader could follow, and, in a field
        that only cites, the ID of a record the ledger holds written bare."""
        if not isinstance(value, str):
            self.add(f"{where} needs text")
            return ""
        unknown = [m[1] for m in KEY_REFERENCE.finditer(value)
                   if m[1] not in keys and not RECORD_ID.fullmatch(m[1])]
        if unknown:
            self.add(
                f"{where}: {', '.join(f'[[{key}]]' for key in unknown)} is no key of this submission")
        if bare := [word for word in BARE_REFERENCE.findall(KEY_REFERENCE.sub("", value))
                    if (word in keys and not RECORD_ID.fullmatch(word))
                    or (citing and (word in keys or word in self.held))]:
            word = bare[0]
            # A key and a word can look alike, such as s3 and Amazon S3: say
            # which word, and how to keep it a word.
            self.add(f"{where}: {word} is written bare: write a reference in double brackets, [[{word}]]"
                     + (f"; if it is a word, such as a product's name, write it in capitals, {word.upper()}"
                        if word != word.upper() else ""))
        return KEY_REFERENCE.sub(lambda m: citation(keys.get(m[1], m[1])) if m[1] in keys or RECORD_ID.fullmatch(m[1])
                                 else m[0], value)

    def put(self, lines, table, ident, cells, where, keys):
        """Write the row `ident` of `table`, recording its problem, named by
        its key, at `where`; returns the values written."""
        if ident is None:
            return []
        written = self.guard(where, lambda: put_row(
            lines, table, ident, cells))
        if written is None:
            back = {ident: f"[[{key}]]" for key, ident in keys.items()}
            self.found[-1] = re.sub(rf"\b{RECORD_ID.pattern}\b",
                                    lambda m: back.get(m[0], m[0]), self.found[-1])
            return []
        return written


def design_rows(lines):
    """The current system design as a design submission, each row keyed by its
    ID, so it can be changed and submitted again."""
    def fields(table, row):
        # The script's own columns, such as an identity's State, aren't submitted.
        cells = dict(zip(TABLES[table][1][1:], row[1:]))
        return dict(zip(FIELDS[table], (as_written(lines, cells[column]) for column in input_columns(table))))
    return {table: [{"key": f"[[{row[0]}]]", **fields(table, row)} for row in table_rows(lines, table)]
            for table in DESIGN_ORDER}
