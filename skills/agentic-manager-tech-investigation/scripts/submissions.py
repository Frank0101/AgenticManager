"""Checks a task's submission and writes everything it implies to the ledger.

The agent never writes an ID, a table or a question's state: a submission cites
every record in double brackets, a new one by a key ([[f1]]) and one the ledger
holds by its ID ([[F07]]), and the script assigns the IDs, moves the queue and
keeps the ledger in step. A
submission is written whole or not at all: it is applied to a copy, every
problem is collected by field, and the ledger changes only when there is none.
"""
import re

from common import OUTSIDE_SCOPE, ids, read_in_part, USER_DECIDED, USER_QUESTION, citation, claim_length_problem
from ledger import (TABLES, as_written, duplicate_of, finish_write, find_row,
                    header_of, move_row, next_id, put_row, refuse_cited, search_reference, set_design_basis,
                    add_scope, table_rows, write_rows, record_review)

# A submission's fields for each kind of record, in the order of the ledger's
# columns after the ID: the script writes the cells from them.
FIELDS = {
    "sources": ["kind", "reference", "revision", "coverage", "superseded_by"],
    "findings": ["claim", "sources", "limits"],
    "gaps": ["gap", "established_and_missing", "would_close", "blocked_by", "authority", "owner_and_next_check"],
    "decisions": ["decision", "position", "candidates_and_constraints", "authority", "owner_and_next_check"],
    "boundaries": ["name", "kind", "evidence"],
    "identities": ["name", "kind", "reaches", "evidence"],
    "components": ["name_and_type", "responsibility", "code", "status", "how_much_was_read", "evidence",
                   "next_steps", "boundary"],
    "connections": ["from", "to", "how", "data", "waits_for_reply", "identity", "state", "evidence"],
    "flows": ["entry_point", "connections", "evidence"],
}
# Fields a submission may leave out, with the value written then.
DEFAULTS = {"superseded_by": "None"}
# The user's answers on whether the investigation covers something.
SCOPE_ANSWERS = ("include", "mention only", "exclude")
# A key names a record new in this submission: its table's letter, in lower
# case, and a number, so it can't be taken for an ID. It is cited as [[s1]],
# which stands out in any field, so every citation of one is found and replaced,
# and none is left in the ledger pointing nowhere.
KEY_REFERENCE = re.compile(r"\[\[([A-Za-z]\d+)\]\]")
BARE_REFERENCE = re.compile(r"\b[A-Za-z]\d+\b")
RECORD_ID = re.compile(r"[A-Z]\d{2,}")
# The fields that only cite other records, where a key written bare, not as
# [[s1]], is refused.
CITING = {"sources": ["superseded_by"], "findings": ["sources"], "boundaries": ["evidence"],
          "identities": ["evidence"], "components": ["evidence", "boundary"],
          "connections": ["from", "to", "identity", "evidence"], "flows": ["connections", "evidence"],
          "questions": ["raised_by", "depends_on"]}
QUESTION_FIELDS = ["raised_by", "question", "depends_on"]
# The order design tables are written in, so each row's citations exist.
DESIGN_ORDER = ["boundaries", "identities",
                "components", "connections", "flows"]


def submit_scope(lines, data, asked):
    """Write the user's decision on each question for them of `asked`, the
    IDs handed out, to the Boundary section, close each with it, and add the
    research questions an included one opens; returns {key: ID}."""
    problems = Problems()
    problems.only(data, ["decisions", "new_questions"])
    decisions = problems.items(data, "decisions")
    questions = problems.items(data, "new_questions", required=False)
    ids = Allocator(lines)
    keys = {}
    for number, item in enumerate(questions):
        ids.claim(keys, "questions", item,
                  f"new_questions[{number}]", problems)
    written = []
    decided = set()
    for number, item in enumerate(decisions):
        where = f"decisions[{number}]"
        problems.only(item, ["question", "name", "answer"], where)
        question = referenced(item.get("question"))
        if question not in asked:
            problems.add(f"{where}.question is one of the questions handed out: "
                         + ", ".join(f"[[{ident}]]" for ident in asked))
            continue
        if question in decided:
            problems.add(f"{where}.question [[{question}]] is decided twice")
            continue
        decided.add(question)
        name = problems.text(item, "name", where)
        answer = problems.text(item, "answer", where)
        if answer and answer not in SCOPE_ANSWERS:
            problems.add(
                f"{where}.answer is one of: {', '.join(SCOPE_ANSWERS)}")
            continue
        if name and answer:
            written += problems.guard(where, lambda n=name,
                                      a=answer: add_scope(lines, n, a)) or []
            problems.guard(where, lambda q=question, a=answer: move_row(
                lines, q, "queue-completed", {"Findings": f"{USER_DECIDED}{a}"}))
    written += add_questions(lines, questions, keys, problems)
    problems.stop()
    problems.guard("the decisions", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


def submit_research(lines, question, data):
    """Write an answer to `question`: its sources, findings and new questions,
    then close it, as answered or blocked; returns {key: ID} and the questions
    blocked with it."""
    problems = Problems()
    problems.only(data, ["sources", "findings", "new_questions", "outcome"])
    ids = Allocator(lines)
    written = []
    sources = problems.items(data, "sources", required=False)
    findings = problems.items(data, "findings", required=False)
    questions = problems.items(data, "new_questions", required=False)
    outcome = data.get("outcome") if isinstance(data, dict) else None
    # Every key first, so records can cite each other in any order. A source
    # read again keeps its ID, its coverage now what was read in all.
    keys = {}
    for number, item in enumerate(sources):
        ids.claim(keys, "sources", item,
                  f"sources[{number}]", problems, same=read_before(lines, item))
    for table, items in (("findings", findings), ("questions", questions)):
        for number, item in enumerate(items):
            ids.claim(keys, table, item, f"{label(table)}[{number}]", problems)
    for number, item in enumerate(sources):
        where = f"sources[{number}]"
        cells = problems.cells(item, "sources", where, keys, extra=["key"])
        if cells is not None and isinstance(cells[1], dict):
            cells[1] = problems.guard(
                where, lambda c=cells: search_reference(c[1]))
        if cells is not None and cells[1] is not None:
            written += problems.put(lines, "sources",
                                    keys.get(key_of(item)), cells, where, keys)
    for number, item in enumerate(findings):
        where = f"findings[{number}]"
        cells = problems.cells(item, "findings", where,
                               keys, extra=["key"])
        if cells is None:
            continue
        check_partial(lines, cells, where, problems, keys)
        if too_long := claim_length_problem(where, cells[0]):
            problems.add(too_long)
        written += problems.put(lines, "findings",
                                keys.get(key_of(item)), cells, where, keys)
    written += add_questions(lines, questions, keys, problems)
    written += close(lines, question, outcome, keys, ids, problems)
    problems.stop()
    blocked = problems.guard(
        "the answer", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys), "blocked": blocked}


def submit_design(lines, data, basis):
    """Replace the system design with the one submitted, keeping the IDs given
    as keys and assigning new ones, then add its new questions and record
    `basis`, what it was built from; returns {key: ID}."""
    problems = Problems()
    problems.only(data, [*DESIGN_ORDER, "new_questions"])
    ids = Allocator(lines)
    before = {table: {row[0] for row in table_rows(
        lines, table)} for table in DESIGN_ORDER}
    items = {table: problems.items(data, table, required=False)
             for table in DESIGN_ORDER}
    questions = problems.items(data, "new_questions", required=False)
    keys = {}
    for table in DESIGN_ORDER:
        for number, item in enumerate(items[table]):
            ids.claim(keys, table, item,
                      f"{table}[{number}]", problems, keep=before[table])
    for number, item in enumerate(questions):
        ids.claim(keys, "questions", item,
                  f"new_questions[{number}]", problems)
    for table in DESIGN_ORDER:
        write_rows(lines, table, [], header_of(lines, table))
    written = []
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
    set_design_basis(lines, basis)
    problems.guard("the design", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


def submit_review(lines, data, round_number):
    """Record review round `round_number`: the questions it raised, added to
    the queue, or the user's choice to stop; returns {key: ID}."""
    problems = Problems()
    if isinstance(data, dict) and "stopped" in data:
        problems.only(data, ["stopped"])
        stopped = problems.text(data, "stopped")
        problems.stop()
        record_review(lines, stopped=stopped)
        return {"ids": {}}
    problems.only(data, ["raised"])
    raised = problems.items(data, "raised", required=False)
    ids = Allocator(lines)
    keys = {}
    for number, item in enumerate(raised):
        ids.claim(keys, "questions", item, f"raised[{number}]", problems)
    for item in raised:
        if isinstance(item, dict):
            item.setdefault("raised_by", f"Review round {round_number}")
    written = add_questions(lines, raised, keys, problems, where="raised")
    problems.stop()
    record_review(lines, list(keys.values()))
    problems.guard("the review", lambda: finish_write(lines, written))
    problems.stop()
    return {"ids": written_keys(keys)}


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


def label(table):
    """The submission's name for a list of `table`'s records."""
    return "new_questions" if table == "questions" else table


def check_partial(lines, cells, where, problems, keys):
    """Record a finding citing a source read only in part whose Limits don't
    cite it too, saying why the unread part can't change the claim: the reason
    sits beside the other limits, where a reader of the finding looks."""
    partly = {row[0]
              for row in table_rows(lines, "sources") if read_in_part(row)}
    cited = [ident for ident in ids(cells[1], "S") if ident in partly]
    missing = [ident for ident in dict.fromkeys(
        cited) if not re.search(rf"\b{ident}\b", cells[2])]
    if missing:
        named = {ident: f"[[{key}]]" for key, ident in keys.items() if ident}
        sources = ", ".join(
            named.get(ident) or f"[[{ident}]]" for ident in missing)
        problems.add(f"{where}: cites {sources}, read only in part: read the rest, or say in limits, citing "
                     f"{sources}, why the unread part can't change the claim")


def add_questions(lines, questions, keys, problems, where="new_questions"):
    """Write each new question as a ready one, one with "for": "user" as a
    question for the user; returns the values written."""
    written = []
    for number, item in enumerate(questions):
        at = f"{where}[{number}]"
        cells = problems.cells(item, "questions", at,
                               keys, extra=["key", "for"])
        if cells is not None and item.get("for", "user") != "user":
            problems.add(
                f'{at}.for is "user", for a question only the user can answer, or left out')
        elif cells is not None:
            if item.get("for") == "user":
                cells[1] = USER_QUESTION + cells[1]
            written += problems.put(lines, "queue-ready",
                                    keys.get(key_of(item)), [*cells, ""], at, keys)
    return written


def close(lines, question, outcome, keys, ids, problems):
    """Close `question` as `outcome` says: answered, with the findings that
    answer it and any other question the same reading answered, or blocked by
    a gap or decision, new or held; returns the values written."""
    if not isinstance(outcome, dict) or len(set(outcome) & {"answered", "blocked", "outside_scope"}) != 1:
        problems.add('outcome is {"answered": "[[f1]], [[F07]]"}, {"blocked": ...}: a gap {"gap": {...}}, a '
                     'decision {"decision": {...}}, or one the ledger holds, "[[G02]]", or {"outside_scope": '
                     '{"decided_in": "[[Q06]]", "name": "..."}}, the question for the user whose answer leaves it out')
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
        ident = ids.next(table[0].upper())
        cells = problems.cells(
            blocked[kind], table, f"outcome.blocked.{kind}", keys)
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
    """Close `question` as outside the scope a decision of the user's leaves
    out, and add what it leaves out to the Boundary section, under that
    decision, so every later task sees it beside the user's own decisions;
    returns the values written."""
    problems.only(outcome, ["outside_scope"], "outcome")
    given = outcome["outside_scope"]
    shape = ('outcome.outside_scope is {"decided_in": "[[Q06]]", "name": "<what this question would research, '
             'briefly>"}, the question for the user whose answer leaves it out')
    if not isinstance(given, dict) or set(given) != {"decided_in", "name"}:
        problems.add(shape)
        return []
    decided = referenced(given["decided_in"])
    row = {row[0]: row for row in table_rows(
        lines, "queue-completed")}.get(decided or "")
    answer = row[-1].removeprefix(
        USER_DECIDED) if row and row[2].startswith(USER_QUESTION) else ""
    if answer not in ("mention only", "exclude"):
        problems.add(f"outcome.outside_scope.decided_in: {given['decided_in']} is no question the user decided as "
                     "mention only or exclude")
        return []
    name = problems.text(given, "name", "outcome.outside_scope")
    if not name:
        return []
    cited = citation(decided)
    written = problems.guard("outcome", lambda: add_scope(
        lines, f"{name}, under {cited}", answer)) or []
    problems.guard("outcome", lambda: move_row(lines, question, "queue-completed",
                                               {"Findings": f"{OUTSIDE_SCOPE}{cited}"}))
    return [*written, cited]


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

    def __init__(self):
        self.found = []

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
            if name == "reference" and isinstance(value, dict):
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
        record, recording a key no record of the submission has, and, in a
        field that only cites, an ID or key written bare, which is prose."""
        if not isinstance(value, str):
            self.add(f"{where} needs text")
            return ""
        unknown = [m[1] for m in KEY_REFERENCE.finditer(value)
                   if m[1] not in keys and not RECORD_ID.fullmatch(m[1])]
        if unknown:
            self.add(
                f"{where}: {', '.join(f'[[{key}]]' for key in unknown)} is no key of this submission")
        if citing and (bare := BARE_REFERENCE.findall(KEY_REFERENCE.sub("", value))):
            self.add(
                f"{where}: write each reference in double brackets, such as [[{bare[0]}]]")
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
            self.found[-1] = re.sub(r"\b[A-Z]\d{2,}\b",
                                    lambda m: back.get(m[0], m[0]), self.found[-1])
            return []
        return written


def design_rows(lines):
    """The current system design as a design submission, each row keyed by its
    ID, so it can be changed and submitted again."""
    return {table: [{"key": f"[[{row[0]}]]", **dict(zip(FIELDS[table], (as_written(lines, cell) for cell in row[1:])))}
                    for row in table_rows(lines, table)] for table in DESIGN_ORDER}
