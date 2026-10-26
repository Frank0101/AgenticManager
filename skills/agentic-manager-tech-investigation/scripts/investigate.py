"""Runs an investigation as a state machine: next hands out a task, submit takes its answer.

The tasks are worked out from the ledger every time, never stored, so they can't
drift from it: the research questions, those for the user asked first, all
together, while research that doesn't wait on their answers goes on; then the
system design once none is open, built again whenever research has added to
what it rests on; then the review rounds, the report and the handover.
A task holds everything needed to do it, so it can go to a subagent as printed.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile

from common import (CONTENT, group_of, ids, read_in_part, FOLDER_NAME, LEDGER, REPORT_SUFFIX, TABLE_HEADINGS, SCOPE_QUESTION, investigation_dir,
                    last_review,
                    ledger_rows, plain, reviewed, stops_on_failure, strip_anchors, topic_of, write_output_file)
from init_investigation import init, usable_sources
from ledger import (as_written, basis, brief, design_basis, depends_on, load, move_row, save, scope_decisions,
                    table_rows)
from submissions import design_rows, submit_research, submit_scope, submit_design, submit_review
import check_report
import make_report
import protocol

# A question's task, such as research:Q03.
RESEARCH_TASK = re.compile(r"research:(Q\d+)")
# Beside a source read only in part, in a research task: the rule a finding
# citing it must meet, where the agent sees the source.
PARTIAL_NOTE = " (read in part: a finding citing it says in limits, citing it, why the rest can't change the claim)"
# What separates tasks handed out together.
SEPARATOR = "\n\n" + "=" * 72 + "\n\n"


def start(topic):
    """Create the investigation's folder and ledger; the result tells the agent
    how to go on."""
    result = init(topic)
    result["next"] = f"{call()} next --investigation {result['investigation']}"
    return result


@contextlib.contextmanager
def locked(relative):
    """Hold the investigation's lock while the block reads and writes its
    ledger, so subagents submitting at once never write over each other."""
    with open(lock_path(relative), "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def lock_path(relative):
    """The lock file of the investigation `relative`: in the system's temporary
    folder, named after the investigation folder's path, so the output folder holds only the
    investigation's own files."""
    folder, _, _ = investigation_dir(relative)
    digest = hashlib.sha256(os.path.realpath(
        folder).encode("utf-8")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"tech-investigation-{digest}.lock")


def next_tasks(relative, maximum=1, resume=False):
    """The text of the next tasks, each question in it moved to in progress:
    the scope questions, as one task, when any is new or nothing else is left;
    else up to `maximum` ready research questions, those that don't wait on
    the user's answers. A question in progress is someone's already, so it is
    handed out again only with `resume`, as after a break; one task in any
    other phase."""
    lines = load(relative).split("\n")
    phase = phase_of(relative, lines)
    if phase != "research":
        return render(relative, lines, task_of(lines, phase))
    if scope_due(lines):
        for row in scope_questions(table_rows(lines, "queue-ready")):
            move_row(lines, row[0], "queue-in-progress")
        save(relative, lines)
        return render(relative, lines, "scope")
    research = [row for row in questions_to_work(
        lines) if not is_scope_question(row)]
    working = [row for row in research if row in table_rows(
        lines, "queue-in-progress")]
    handed = (working if resume else [
              row for row in research if row not in working])[:maximum]
    if not handed:
        return (f"Nothing new to hand out: {', '.join(row[0] for row in working)} in progress. Run next again once "
                "an answer is submitted; if no one is working on them, as after a break, run next with --resume.")
    for row in handed:
        if row not in working:
            move_row(lines, row[0], "queue-in-progress")
    save(relative, lines)
    return SEPARATOR.join(render(relative, lines, f"research:{row[0]}") for row in handed)


def submit(relative, task, data):
    """Check and write the answer `data` to `task`, which must be one the
    investigation hands out now; returns what was written."""
    lines = load(relative).split("\n")
    phase = phase_of(relative, lines)
    current = task_of(lines, phase)
    if task == "write" and phase == "write":
        return submit_report(relative, data)
    if (match := RESEARCH_TASK.fullmatch(task)) and phase == "research":
        research = [row for row in questions_to_work(
            lines, all_open=True) if not is_scope_question(row)]
        if match[1] not in {row[0] for row in research}:
            raise SystemExit(
                f"{match[1]} isn't an open research question: run next")
        result = submit_research(lines, match[1], data)
    elif task == "scope" and (asked := scope_questions(questions_to_work(lines))):
        result = submit_scope(lines, data, [row[0] for row in asked])
    elif task != current:
        raise SystemExit(
            f"{task} isn't a task now; the task now is {current}: run next")
    elif phase == "design":
        result = submit_design(lines, data, basis(lines))
    elif phase == "review":
        result = submit_review(lines, data, len(rounds(lines)) + 1)
    else:
        raise SystemExit("the investigation is finished: nothing to submit")
    save(relative, lines)
    return {"ok": True, "task": task, **result, "next": f"{call()} next --investigation {relative}"}


def phase_of(relative, lines):
    """Where the investigation stands: research, design, review, write or
    finished, worked out from the ledger and the report."""
    if questions_to_work(lines):
        return "research"
    if design_basis(lines) != basis(lines):
        return "design"
    if not reviewed(rounds(lines)):
        return "review"
    if report_problems(relative) != []:
        return "write"
    return "finished"


def questions_to_work(lines, all_open=False):
    """The questions to work, in the queue's order: those in progress, then
    the ready ones whose dependencies are all completed; with `all_open`,
    every ready one too."""
    completed = {row[0] for row in table_rows(lines, "queue-completed")}
    ready = [row for row in table_rows(
        lines, "queue-ready") if all_open or set(depends_on(row)) <= completed]
    return table_rows(lines, "queue-in-progress") + ready


def scope_questions(rows):
    """The scope questions of `rows`, which only the user can answer."""
    return [row for row in rows if is_scope_question(row)]


def is_scope_question(row):
    """Whether the queue row `row` is a scope question."""
    return row[2].startswith(SCOPE_QUESTION)


def task_of(lines, phase):
    """The one task of `phase`: in research, asking the user when it is due,
    else the first research question's answer."""
    if phase == "research":
        if scope_due(lines):
            return "scope"
        return f"research:{next(row for row in questions_to_work(lines) if not is_scope_question(row))[0]}"
    return {"review": f"review:{len(rounds(lines)) + 1}"}.get(phase, phase)


def scope_due(lines):
    """Whether to ask the user now: a question for them is new, not yet asked,
    or nothing but their questions is left to work. Research that doesn't wait
    on their answers goes on meanwhile, so a run continues while they are away."""
    open_questions = questions_to_work(lines)
    asked = scope_questions(open_questions)
    new = [row for row in asked if row in table_rows(lines, "queue-ready")]
    return bool(new) or (bool(asked) and len(asked) == len(open_questions))


def render(relative, lines, task):
    """The full text of `task`: what to do, what the ledger holds for it, and
    the command that submits it."""
    head = [f"# Task {task}", ""]
    values = fills(relative)
    if task == "scope":
        body = [protocol.text("scope", **values), "", *scope_context(lines)]
    elif task.startswith("research:"):
        body = [protocol.text("research", **values), "", *question_context(lines, task.removeprefix("research:")),
                "", "A blocked answer has this outcome instead:",
                json.dumps(protocol.example("research-blocked"), ensure_ascii=False)]
    elif task == "design":
        body = [protocol.text("design", **values), "", *design_context(lines)]
    elif task.startswith("review:"):
        number = int(task.removeprefix("review:"))
        body = [protocol.text("review", **values)]
        if number > protocol.REVIEW_ROUNDS:
            body += ["", protocol.text("review-ask", round=number, rounds=number - 1, **values), "",
                     *(f"- Round {row[0]} raised: {plain(row[-1])}" for row in rounds(lines))]
        if last := last_review(rounds(lines)):
            body += ["",
                     f"The last round raised {plain(last)}; they are answered or blocked now."]
    elif task == "write":
        body = [protocol.text("write", **values), ""]
        if problems := report_problems(relative):
            body += ["## Problems with the last text submitted",
                     "", *(f"- {p}" for p in problems), ""]
        body += ["## The brief", "", strip_anchors(brief(lines))]
    else:
        folder, _, temporary = investigation_dir(relative)
        return "\n".join([*head, protocol.text("finished", **values), "",
                          f"- The report: {os.path.join(folder, topic_of(folder) + REPORT_SUFFIX)}",
                          f"- The ledger: {values['ledger']}",
                          f"- The folder is {'temporary' if temporary else 'kept'}"])
    name = task.partition(":")[0]
    example = protocol.compact(protocol.example(name))
    if task == "write":
        command = [f"{call()} submit --investigation {relative} --task write --input <your file>", "",
                   "The file's shape:", example]
    else:
        command = [
            f"{call()} submit --investigation {relative} --task {task} <<'EOF'", example, "EOF"]
    return "\n".join([*head, *body, "", "## Submit", "",
                      "Submit the answer with this command, the JSON replaced by yours; the example shows its "
                      "fields:", "", *command])


def fills(relative):
    """The values the protocol names for this investigation: the scripts' and
    the library's folders, written as the commands the skill pre-approves need
    them, the investigation, its topic and its ledger, and the sources the
    config enables for the documentation and the code."""
    scripts = os.path.dirname(script_path())
    folder, _, _ = investigation_dir(relative)
    sources = usable_sources()
    return {"scripts": scripts, "investigation": relative, "ledger": os.path.join(folder, LEDGER),
            "topic": topic_of(folder).replace("-", " "),
            "documentation": " or ".join(f"the {name} source" for name in sources["documentation"]),
            "code": " or ".join(f"the {name} source" for name in sources["source_control"]),
            "lib": os.path.join(os.path.dirname(scripts), "..", "agentic-manager-utils-lib", "agentic_manager")}


def scope_context(lines):
    """What asking the user needs: each question for them handed out, what
    raised it, and the decisions they made so far."""
    out = ["## The questions", ""]
    out += [f"- {row[0]}: {plain(row[2]).removeprefix(SCOPE_QUESTION)} (raised by {plain(row[1])})"
            for row in scope_questions(questions_to_work(lines))]
    return out + ["", "## Decided so far", "", *(scope_decisions(lines) or ["None yet."])]


def question_context(lines, ident):
    """What the ledger holds for the question `ident`: the question, what
    raised it, the scope decided so far, the answers it builds on, the other
    open questions, and every source already read."""
    _, row = next((name, row) for name in ("queue-in-progress", "queue-ready") for row in table_rows(lines, name)
                  if row[0] == ident)
    findings = {row[0]: row for row in table_rows(lines, "findings")}
    completed = {row[0]: row for row in table_rows(lines, "queue-completed")}
    out = ["## The question", "", f"{ident}: {plain(row[2])}", f"Raised by: {plain(row[1])}",
           "", "## The scope the user decided so far", "", *(scope_decisions(lines) or ["None yet."])]
    builds_on = [f for f in ids(strip_anchors(row[1]), "F") if f in findings]
    for need in depends_on(row):
        builds_on += [f for f in ids(strip_anchors(
            completed.get(need, [""])[-1]), "F") if f in findings]
    if builds_on:
        out += ["", "It builds on these findings:"]
        out += [f"- {f}: {plain(findings[f][1])} ({plain(findings[f][2])})" for f in dict.fromkeys(builds_on)]
    out += ["", "## Other open questions", "",
            "Don't raise one of these again: each is answered in its own task.", ""]
    out += [f"- {other[0]}: {plain(other[2])}" for name in ("queue-in-progress", "queue-ready", "queue-blocked")
            for other in table_rows(lines, name) if other[0] != ident] or ["None."]
    out += ["", "## Sources already read", ""]
    out += [f"- {row[0]}: {plain(row[1])}; {as_written(lines, row[2])}; {plain(row[3])}; coverage: {plain(row[4])}"
            + (PARTIAL_NOTE if read_in_part(row) else "")
            for row in table_rows(lines, "sources")] or ["None yet."]
    return out


def design_context(lines):
    """What the design is built from: the scope the user decided, every
    finding, gap and decision, the code sources with their coverage, and the
    current design to change."""
    out = ["## The scope the user decided", "", *
           (scope_decisions(lines) or ["None yet."]), "", "## Findings", ""]
    out += [f"- {row[0]}: {plain(row[1])} ({plain(row[2])}) Limits: {plain(row[3])}"
            for row in table_rows(lines, "findings")] or ["None."]
    for name in ("gaps", "decisions"):
        out += ["", f"## {name.capitalize()}", ""]
        out += [f"- {row[0]}: " + "; ".join(plain(cell) for cell in row[1:]) for row in table_rows(lines, name)] \
            or ["None."]
    out += ["", "## Code read, with its coverage", ""]
    out += [f"- {row[0]}: {as_written(lines, row[2])} at {plain(row[3])}; coverage: {plain(row[4])}"
            for row in table_rows(lines, "sources") if group_of(row) == "source_control"] or ["None."]
    current = design_rows(lines)
    if any(current.values()):
        out += ["", "## The current design, to change and submit again whole", "",
                json.dumps(current, ensure_ascii=False, indent=2)]
    return out


def rounds(lines):
    """The review table's rows."""
    return ledger_rows("\n".join(lines), TABLE_HEADINGS["reviews"])


def report_problems(relative):
    """What stops the report passing its final check: [] once it does, the
    problems of the text submitted while it doesn't, or None before any."""
    folder, _, _ = investigation_dir(relative)
    report = os.path.join(folder, topic_of(folder) + REPORT_SUFFIX)
    if os.path.isfile(report):
        checked = check_report.check_report(report, handover=True)
        return [] if checked["ok"] else checked["errors"]
    if os.path.isfile(os.path.join(folder, CONTENT)):
        return make_report.content_problems(relative) or ["the report wasn't generated: submit the text again"]
    return None


def submit_report(relative, data):
    """Write content.json, generate the report from it and run the final
    check; exits with the problems unless the report passes."""
    if not isinstance(data, dict):
        raise SystemExit(
            "the text is a JSON object, in the shape the write task shows")
    folder, _, _ = investigation_dir(relative)
    # A report left by an earlier submission is replaced, never checked again.
    old = os.path.join(folder, topic_of(folder) + REPORT_SUFFIX)
    if os.path.isfile(old):
        os.remove(old)
    write_output_file(FOLDER_NAME, f"{relative}/{CONTENT}",
                      json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    made = make_report.make_report(relative)
    checked = check_report.check_report(made["path"], handover=True)
    if not checked["ok"]:
        raise SystemExit("the report doesn't pass its final check; fix each of these and submit again:\n- "
                         + "\n- ".join(checked["errors"]))
    return {"ok": True, "task": "write", "path": made["path"], "temporary": made["temporary"],
            "warnings": list(dict.fromkeys(made["warnings"] + checked["warnings"])),
            "next": f"{call()} next --investigation {relative}"}


def call():
    """The command that runs this script."""
    return f"python3 {script_path()}"


def script_path():
    """This script's path as the agent ran it, so every command it is told to
    run next matches the path the skill pre-approves."""
    return os.path.abspath(sys.argv[0]) if sys.argv[0].endswith("investigate.py") else os.path.abspath(__file__)


def read_input(path):
    """The submission, from the file `path` or standard input, as JSON."""
    try:
        if path:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        return json.loads(text)
    except OSError as error:
        raise SystemExit(f"--input: cannot read {path}: {error.strerror}")
    except ValueError as error:
        raise SystemExit(f"the submission is not valid JSON: {error}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run an investigation: start it, then repeat next, do the task, submit, until next says it is "
        "finished.")
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start", help="create the investigation's folder and ledger",
                                description="Create the investigation's folder, <Topic>_<YY-MM-DD>, replacing one of "
                                "the same topic and day, and its ledger. Prints one line of JSON: the investigation's "
                                "name, its folder, whether it is temporary, the sources it uses, the approved "
                                "examples, and the command to run next.")
    begin.add_argument("--topic", required=True,
                       help="capitalised words or acronyms joined by hyphens, such as Payments-Retry-Service")
    take = commands.add_parser("next", help="print the next task, or up to --max research questions",
                               description="Print the next task: what to do, what the ledger holds for it and the "
                               "command that submits it.")
    take.add_argument("--investigation", required=True,
                      help="<Topic>_<YY-MM-DD>, as start printed it")
    take.add_argument("--max", type=int, default=1,
                      help="how many research questions at most, such as 4 to give each to a subagent")
    take.add_argument("--resume", action="store_true",
                      help="hand out the research questions in progress again, when no one is working on them, "
                      "as after a break")
    give = commands.add_parser("submit", help="check a task's answer and write it",
                               description="Check a task's answer, given as JSON on standard input or in --input, "
                               "and write everything it implies; nothing is written while any problem is left, but for the "
                               "report's text, and each problem is named by its field. Each task next prints ends with its answer's shape and "
                               "the command to copy. Prints one line of JSON.")
    give.add_argument("--investigation", required=True,
                      help="<Topic>_<YY-MM-DD>, as start printed it")
    give.add_argument("--task", required=True,
                      help="the task's name, as next printed it, such as research:Q03")
    give.add_argument(
        "--input", help="a file holding the answer, instead of standard input")
    args = parser.parse_args(argv)
    with stops_on_failure():
        if args.command == "start":
            print(json.dumps(start(args.topic)))
        elif args.command == "next":
            with locked(args.investigation):
                print(next_tasks(args.investigation,
                      max(1, args.max), args.resume))
        else:
            data = read_input(args.input)
            with locked(args.investigation):
                print(json.dumps(submit(args.investigation,
                      args.task, data), ensure_ascii=False))


if __name__ == "__main__":
    main()
