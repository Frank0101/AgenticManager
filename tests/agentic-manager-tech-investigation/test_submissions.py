"""Unit tests for skills/agentic-manager-tech-investigation/scripts/submissions.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

Each test starts a new investigation in a temporary output folder and submits
answers to it, as investigate.py does, then reads the ledger back.
"""

import copy
import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
import init_investigation  # noqa: E402
import ledger  # noqa: E402
import submissions  # noqa: E402
import protocol  # noqa: E402
import common  # noqa: E402
from common import ID_LETTERS  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, temp_output  # noqa: E402

GAP = {"gap": "Billing callers", "missing": "The API is merged; its callers aren't read",
       "would_close": "Read access", "blocked_by": "No access (billing repository)", "evidence": "[[F01]]",
       "owner_and_next_check": "Billing team"}


def finding(key="[[f1]]", claim="Search reads the index.", sources="[[S01]]", **more):
    """A finding as a submission gives it."""
    return {"key": key, "claim": claim, "sources": sources, "limits": "None", **more}


class SubmissionTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=date(2026, 10, 5))
        self.path = Path(self.folder) / INVESTIGATION / "ledger.md"

    def submit(self, kind, *args):
        """Submit to the ledger as investigate.py does: saved only when the
        submission is accepted; returns its result."""
        lines = self.text().split("\n")
        result = getattr(submissions, f"submit_{kind}")(lines, *args)
        ledger.save(INVESTIGATION, lines)
        return result

    def refused(self, kind, *args):
        """The problems a refused submission lists, after checking it wrote nothing."""
        before = self.text()
        with self.assertRaises(SystemExit) as stopped:
            self.submit(kind, *args)
        self.assertEqual(self.text(), before)
        message = str(stopped.exception.code)
        self.assertTrue(message.startswith("nothing was written"), message)
        return message

    def text(self):
        return self.path.read_text(encoding="utf-8")

    def plain(self):
        return re.sub(rf"\[([{ID_LETTERS}]\d+)\]\(#[a-z]+\d+\)", r"\1", re.sub(r'<a id="[^"]+"></a>', "", self.text()))

    def rows(self, table):
        return [row[0] for row in ledger.table_rows(self.text().split("\n"), table)]

    def answered(self, question="Q01", **data):
        """Answer `question` with one source and the findings given, or one."""
        data.setdefault("sources", [{"key": "[[s1]]", "kind": "code", "reference": "[api](https://example.com/api)",
                                     "revision": "abc", "coverage": {"read": "full"}}])
        data.setdefault("findings", [finding(sources="[[s1]]")])
        data.setdefault("outcome", {"answered": "[[f1]]"})
        return self.submit("research", question, data)

    def test_the_users_decisions_are_scope_boundaries_that_close_their_questions(self):
        self.submit("research", "Q01", copy.deepcopy(
            protocol.example("research")))
        self.assertIn(
            "| Q07 | F01 | Scope boundary: Should the investigation cover the payments gateway", self.plain())
        # name: (the decisions, a problem they list)
        cases = [("a question not handed out", [{"question": "[[Q02]]", "topic": "x", "answer": "include"}],
                  "decisions[0].question is one of the questions handed out: [[Q07]]"),
                 ("an answer not allowed", [{"question": "[[Q07]]", "topic": "x", "answer": "maybe"}],
                  "decisions[0].answer is one of: include, mention only, exclude"),
                 ("a question decided twice", [{"question": "[[Q07]]", "topic": "x", "answer": "exclude"}] * 2,
                  "decisions[1].question [[Q07]] is decided twice"),
                 ("no topic", [{"question": "[[Q07]]", "answer": "exclude"}], "decisions[0].topic needs text")]
        for name, decisions, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused(
                    "scope", {"decisions": decisions}, ["Q07"]))
        self.submit("scope", {"decisions": [{"question": "[[Q07]]", "topic": "The payments gateway",
                                             "answer": "exclude"}]}, ["Q07"])
        self.assertIn("## Scope boundaries\n\n| ID | Topic | Decision | Asked in |\n| --- | --- | --- | --- |\n"
                      "| U01 | The payments gateway | exclude | Q07 |\n\n## Independent reviews", self.plain())
        self.assertIn("| Scope boundary: Should the investigation cover the payments gateway the search API calls for "
                      "paid results? | None | Decided by the user: U01 |", self.plain())
        self.assertEqual(check_report.check_ledger(self.path)[0], [])

    def test_an_answer_writes_its_records_and_closes_the_question(self):
        result = self.submit(
            "research", "Q01", copy.deepcopy(protocol.example("research")))
        self.assertEqual(result["ids"], {
                         "[[s1]]": "S01", "[[s2]]": "S02", "[[f1]]": "F01", "[[f2]]": "F02", "[[q1]]": "Q06",
                         "[[q2]]": "Q07"})
        self.assertEqual(self.rows("sources"), ["S01", "S02"])
        self.assertEqual(self.rows("findings"), ["F01", "F02"])
        self.assertEqual(self.rows("queue-completed"), ["Q01"])
        self.assertIn("| Q01 | Seed (documentation) |", self.plain())
        self.assertIn("| F01, F02 |", self.plain().split(
            "### Completed")[1].split("###")[0])
        # A new question is ready, raised by the finding that raised it.
        self.assertIn(
            "| Q06 | F01 | Which job builds the search index, and how often? | None |  |", self.plain())
        self.assertEqual(check_report.check_ledger(self.path)[0], [])

    def test_a_source_read_again_keeps_its_id(self):
        self.answered()
        self.answered("Q02", sources=[{"key": "[[s1]]", "kind": "code", "reference": "[the api](https://example.com/api)",
                                       "revision": "abc", "coverage": {"read": "full", "note": "re-read"}}],
                      findings=[finding(claim="Another fact.", sources="[[s1]]")])
        self.assertEqual(self.rows("sources"), ["S01"])
        self.assertIn("| full: re-read | F01, F02 |", self.plain())

    def test_a_source_read_again_only_grows(self):
        # What a read covers is added to what the ledger holds: a later,
        # smaller read never shrinks it.
        file = "[f](https://git.example/acme/api/blob/abc/server.py)"
        # name: (the Coverage held, this read, the Coverage written)
        cases = [("two line ranges", "partial: lines 1-80 of 352", {"read": "partial", "lines": [[200, 240]]}, "partial: lines 1-80, 200-240 of 352"),
                 ("touching ranges join", "partial: lines 1-80",
                  {"read": "partial", "lines": [[81, 120]]}, "partial: lines 1-120"),
                 ("a smaller read", "partial: lines 1-200; routes",
                  {"read": "partial", "lines": [[10, 20]]}, "partial: lines 1-200; routes"),
                 ("then in full", "partial: lines 1-80",
                  {"read": "full"}, "full"),
                 ("full stays full", "full", {
                  "read": "partial", "lines": [[1, 9]]}, "full"),
                 ("more sections", "partial: sections: Proposal", {
                  "read": "partial", "sections": ["Risks"]}, "partial: sections: Proposal, Risks"),
                 ("found after all", "can't access: not on main", {"read": "partial", "lines": [[1, 5]], "note": "x"}, "partial: lines 1-5; not on main; x")]
        for name, held, now, expected in cases:
            with self.subTest(name):
                grown = submissions.grown_coverage(
                    submissions.coverage_fields(held), now)
                self.assertEqual(submissions.coverage_text(grown), expected)
        # Through a submission: the second read keeps the first one's lines,
        # and the source stays superseded, as the second answer doesn't say
        # otherwise.
        source = {"key": "[[s1]]", "kind": "code",
                  "reference": file, "revision": "abc"}
        newer = {"key": "[[s2]]", "kind": "code", "reference": "[g](https://git.example/acme/api/blob/abc/v2.py)",
                 "revision": "abc", "coverage": {"read": "full"}}
        self.answered(sources=[{**source, "coverage": {"read": "partial", "lines": [[1, 80]], "of": 352},
                                "superseded_by": "[[s2]]"}, newer],
                      findings=[finding(sources="[[s1]]", partial={"[[s1]]": "the rest is admin routes"})])
        self.answered("Q02", sources=[{**source, "coverage": {"read": "partial", "lines": [[200, 240]]}}],
                      findings=[finding(sources="[[s1]]", partial={"[[s1]]": "the rest is admin routes"})])
        self.assertEqual(self.rows("sources"), ["S01", "S02"])
        self.assertIn(
            "| partial: lines 1-80, 200-240 of 352 | F01, F02 | S02 |", self.plain())

    def test_references_are_written_in_double_brackets(self):
        # A reference in double brackets, [[F07]] or a key such as [[f1]], is
        # written as a citation in any field, so none is left pointing nowhere;
        # anything else is prose, even a word shaped like an ID.
        self.answered(findings=[finding(), finding("[[f2]]", "P95 latency is 2s.", sources="[[S01]]; [[f1]]",
                                                   limits="Contradicts [[f1]].")])
        self.assertIn(
            "| P95 latency is 2s. | S01; F01 | Contradicts F01. |", self.plain())
        self.assertIn("| P95 latency is 2s. | [S01](#s01); [F01](#f01) | Contradicts [F01](#f01). |",
                      self.text())
        # name: (the findings, a problem they list), the source s1 declared
        DECLARED = [{"key": "[[s1]]", "kind": "code", "reference": "[api](https://example.com/api)",
                     "revision": "abc", "coverage": {"read": "full"}}]
        cases = [("a bare key where a field cites", [finding(sources="[[S01]] and s1")],
                  "s1 is written bare: write a reference in double brackets, [[s1]]; if it is a word, such as a product's name, write it in capitals, S1"),
                 ("a bare ID where a field cites", [finding(sources="S01")],
                  "S01 is written bare: write a reference in double brackets, [[S01]]"),
                 ("a key declared bare", [
                  finding("f1")], "findings[0].key is [[f1]]"),
                 ("a key written bare in prose", [finding(), finding("[[f2]]", "P95 latency is 2s.",
                                                                     limits="Contradicts f1.")],
                  "f1 is written bare: write a reference in double brackets, [[f1]]"),
                 ("a key nothing declares", [
                  finding(limits="See [[f9]].")], "[[f9]] is no key of this submission"),
                 ("an ID the ledger doesn't hold", [finding(sources="[[S09]]")], "cites S09, which the ledger")]
        for name, findings, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused("research", "Q02", {"sources": DECLARED, "findings": findings,
                                                                         "outcome": {"answered": "[[f1]]"}}))
        # In a field that cites, a word shaped like an ID that names no record,
        # such as a page's version, is prose too.
        self.submit("research", "Q02", {"findings": [finding(sources="[[S01]], version V2")],
                                        "outcome": {"answered": "[[f1]]"}})
        self.assertIn("| S01, version V2 |", self.plain())
        # So is a key inside an address, a dotted or hyphenated name, or one in
        # capitals, as the refusal suggests for a word such as S3.
        self.submit("research", "Q03", {"sources": DECLARED, "findings": [
            finding(claim="Exports land in s1://acme-exports, served by s1.example.com from bucket kb-s1 on S1.", sources="[[s1]]")],
            "outcome": {"answered": "[[f1]]"}})
        self.assertIn("Exports land in s1://acme-exports", self.plain())

    def test_a_partial_read_is_explained_for_each_claim(self):
        # A finding citing a source read only in part gives, by source, why
        # the unread part can't change its claim; the script writes the
        # reason into its Limits.
        partial = [{"key": "[[s1]]", "kind": "code", "reference": "[api](https://example.com/api)", "revision": "abc",
                    "coverage": {"read": "partial", "lines": [[1, 80]]}}]
        # name: (the finding's extra fields, a problem they list)
        cases = [("no reason", {}, "findings[0]: cites [[s1]], read only in part: read the rest, or say in partial, "
                  "for [[s1]], why the unread part can't change this claim"),
                 ("a reason in limits only", {"limits": "[[s1]]: the rest is admin routes."},
                  "say in partial, for [[s1]]"),
                 ("a reason for a source it doesn't cite", {"partial": {"[[s1]]": "admin routes", "[[S07]]": "x"}},
                  "findings[0].partial: [[S07]] isn't a source this finding cites that was read only in part"),
                 ("an empty reason", {"partial": {
                  "[[s1]]": " "}}, "findings[0].partial.[[s1]] needs text"),
                 ("not an object", {"partial": "admin routes"}, "findings[0].partial is an object")]
        for name, extra, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused("research", "Q01", {
                    "sources": partial, "findings": [finding(sources="[[s1]]", **extra)],
                    "outcome": {"answered": "[[f1]]"}}))
        self.submit("research", "Q01", {"sources": partial, "findings": [
            finding(sources="[[s1]] (lines 1-40)", limits="The index job not read.",
                    partial={"[[s1]]": "the unread lines are admin routes."}),
            finding("[[f2]]", "Search is public.", sources="[[s1]]",
                    partial={"[[s1]]": "the unread lines are admin routes"})],
            "outcome": {"answered": "[[f1]], [[f2]]"}})
        self.assertIn(
            "| The index job not read. S01 read in part: the unread lines are admin routes. |", self.plain())
        self.assertIn(
            "| S01 | S01 read in part: the unread lines are admin routes. |", self.plain())

    def test_coverage_is_written_from_its_fields(self):
        # name: (coverage, kind, the Coverage written, or the start of the
        # problem): the script writes the text, and a partial read names what
        # was read, by what the source is (common.coverage_problem).
        cases = [("full", {"read": "full"}, "code", "full"),
                 ("lines of a file", {"read": "partial", "lines": [[1, 80], [200, 240]], "of": 352, "note": "routes"},
                  "code", "partial: lines 1-80, 200-240 of 352; routes"),
                 ("files of a pull request", {"read": "partial", "files": ["api/routes.py"]}, "code: pull request",
                  "partial: files: api/routes.py"),
                 ("sections of a page", {"read": "partial", "sections": ["Proposal"]}, "documentation",
                  "partial: sections: Proposal"),
                 ("a path not found", {"read": "can't access", "note": "not on the main branch at abc"}, "code",
                  "can't access: not on the main branch at abc"),
                 ("code in part naming nothing read", {"read": "partial", "note": "routes"}, "code",
                  "S01: Coverage of code read in part names the lines read"),
                 ("a document in part with no sections", {"read": "partial"}, "documentation",
                  "S01: Coverage of a document read in part names the sections read"),
                 ("lines beyond the file", {"read": "partial", "lines": [[300, 400]], "of": 352}, "code",
                  "lines lists the ranges read"),
                 ("a word, not a read", {"read": "skimmed"},
                  "code", "coverage is an object"),
                 ("text", "full", "code", "coverage is an object")]
        for name, given, kind, expected in cases:
            with self.subTest(name):
                try:
                    text = submissions.coverage_text(given)
                except SystemExit as refused:
                    self.assertTrue(str(refused.code).startswith(
                        expected), refused.code)
                    continue
                problem = common.coverage_problem(
                    ["S01", kind, "[x](https://x.example/x)", "abc", text, "", "None"])
                self.assertEqual(problem[:len(expected)]
                                 if problem else text, expected)

    def test_every_problem_is_listed_by_field_and_nothing_is_written(self):
        data = {"sources": [{"key": "[[s1]]", "kind": "source_control", "reference": "[api](https://example.com/api)",
                             "revision": "abc", "coverage": {"read": "skimmed"}}],
                "findings": [finding(sources="[[s1]], [[s9]]"), finding("[[f1]]", "Again."),
                             finding("x2", "word " * 151, sources="[[s1]]")],
                "new_questions": [{"key": "[[q1]]", "question": "Why?", "raised_by": "[[f1]]", "depends_on": "[[Q99]]"}],
                "outcome": {"answered": "[[f1]]"}, "notes": "x"}
        problems = self.refused("research", "Q01", data)
        for expected in ("the submission has no field notes", "sources[0].coverage: coverage is an object",
                         "findings[0].sources: [[s9]] is no key of this submission", "findings[1].key [[f1]] is used twice",
                         "findings[2].key is [[f1]]: f and a number", "claim is 151 words"):
            with self.subTest(expected):
                self.assertIn(expected, problems)

    def test_an_outcome_closes_the_question_one_way(self):
        # name: (outcome, a problem it lists)
        cases = [("none", None, 'outcome is {"answered": "[[f1]], [[F07]]"}, {"blocked": ...}'),
                 ("both", {"answered": "[[f1]]",
                  "blocked": "[[G01]]"}, "outcome is"),
                 ("no finding", {"answered": "None"},
                  "names the findings that answer it"),
                 ("a gap the ledger doesn't hold", {
                  "blocked": "[[G09]]"}, "[[G09]] is no gap or decision the ledger holds"),
                 ("a blocker of another kind", {
                  "blocked": {"note": "x"}}, "outcome.blocked is"),
                 ("a closed question", {"answered": "[[f1]]", "also_answers": {"[[Q01]]": "[[f1]]"}},
                  "only an open question can be closed")]
        for name, outcome, expected in cases:
            with self.subTest(name):
                data = {"findings": [
                    finding(sources="[[S01]]")]} if outcome else {}
                self.answered()  # gives the ledger S01
                self.assertIn(expected, self.refused(
                    "research", "Q02", {**data, "outcome": outcome}))

    def test_a_question_the_users_scope_leaves_out_is_closed_by_it(self):
        # It cites the boundary that leaves it out, and adds no boundary: the
        # user decided only the one they were asked.
        self.submit("research", "Q01", copy.deepcopy(
            protocol.example("research")))
        self.submit("scope", {"decisions": [{"question": "[[Q07]]", "topic": "The payments gateway",
                                             "answer": "mention only"}]}, ["Q07"])
        self.submit("research", "Q02", {
                    "outcome": {"outside_scope": "[[U01]]"}})
        completed = {row[0]: row[-1]
                     for row in ledger.table_rows(self.text().split("\n"), "queue-completed")}
        self.assertEqual(
            completed["Q02"], "Outside the scope decided in [U01](#u01)")
        self.assertEqual([row[0] for row in ledger.table_rows(
            self.text().split("\n"), "scope")], ["U01"])
        self.assertEqual(check_report.check_ledger(self.path)[0], [])
        # name: (the outcome, a problem it lists)
        refused = "is no scope boundary decided as mention only or exclude"
        cases = [("a boundary not in the ledger", "[[U02]]", refused),
                 ("the question, not its boundary", "[[Q07]]", refused),
                 ("not a citation", {"decided_in": "[[U01]]"}, refused)]
        for name, given, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused(
                    "research", "Q03", {"outcome": {"outside_scope": given}}))

    def test_a_blocked_question_blocks_those_that_need_it(self):
        self.answered(findings=[finding(sources="[[s1]]")],
                      new_questions=[{"key": "[[q1]]", "question": "Next?", "raised_by": "[[f1]]", "depends_on": "[[Q02]]"}])
        # A gap traces to what it rests on, as every other record does.
        self.assertIn("outcome.blocked.gap: Evidence names the findings or sources it rests on",
                      self.refused("research", "Q02", {"outcome": {"blocked": {"gap": {**GAP, "evidence": "the code"}}}}))
        self.submit("research", "Q02", {"outcome": {"blocked": {"gap": GAP}}})
        self.assertEqual(self.rows("gaps"), ["G01"])
        self.assertEqual(self.rows("queue-blocked"), ["Q02", "Q06"])
        self.assertIn(
            "| Q02 | Seed (documentation) | What problem does", self.plain())
        # A gap the ledger holds blocks too.
        self.submit("research", "Q03", {"outcome": {"blocked": "[[G01]]"}})
        self.assertEqual(self.rows("queue-blocked"), ["Q02", "Q03", "Q06"])

    def test_the_same_reading_can_answer_another_question(self):
        self.answered(outcome={"answered": "[[f1]]",
                      "also_answers": {"[[Q03]]": "[[f1]]"}})
        self.assertEqual(self.rows("queue-completed"), ["Q01", "Q03"])

    def test_a_design_replaces_the_last_one_and_keeps_ids(self):
        self.answered(sources=[{"key": "[[s1]]", "kind": "tracker", "reference": "[t](https://example.com/t)",
                                "revision": "Done", "coverage": {"read": "full"}}])
        self.submit("research", "Q02", {"outcome": {"blocked": {"gap": GAP}}})
        design = {**copy.deepcopy(protocol.example("design")),
                  "new_questions": []}
        design["components"][0]["code"] = "None"
        design["components"][0]["state"] = "🟨 Planned"
        design["connections"][0]["state"] = "🟨 Planned"
        design["components"][1]["in_the_target"] = "Unchanged"
        result = self.submit("design", design)
        self.assertEqual(result["ids"], {"[[s1]]": "S02", "[[f1]]": "F02", "[[b1]]": "B01", "[[i1]]": "I01",
                                         "[[c1]]": "C01", "[[c2]]": "C02", "[[e1]]": "E01", "[[p1]]": "P01"})
        # What the design read again is recorded as research is, and the
        # design counts as built from it, so it isn't out of date at once.
        self.assertIn("| partial: lines 40-60 of 200 | F02 |", self.plain())
        self.assertEqual(ledger.design_basis(
            self.text().split("\n")), (2, 1, 0))
        # Submitted again with its own IDs, a row is kept; one left out is removed,
        # and a new one takes a number never used.
        current = submissions.design_rows(self.text().split("\n"))
        current["components"] = [current["components"][0], {**current["components"][0], "key": "[[c1]]",
                                                            "name": "Worker", "kind": "job"}]
        current["connections"] = []
        current["flows"] = []
        current["identities"][0]["reaches"] = "read on [[C01]]"
        result = self.submit("design", current)
        self.assertEqual(result["ids"]["[[c1]]"], "C03")
        self.assertEqual(self.rows("components"), ["C01", "C03"])
        self.assertEqual(self.rows("connections"), [])
        self.assertEqual(check_report.check_ledger(self.path)[0], [])

    def test_a_design_row_still_cited_cant_be_left_out(self):
        self.answered(sources=[{"key": "[[s1]]", "kind": "tracker", "reference": "[t](https://example.com/t)",
                                "revision": "Done", "coverage": {"read": "full"}}])
        component = {"key": "[[c1]]", "name": "API", "kind": "service", "responsibility": "r", "code": "None",
                     "state": "🟨 Planned", "evidence": "[[F01]]", "in_the_target": "Unchanged",
                     "boundary": "None"}
        self.submit("design", {"components": [component],
                               "new_questions": [{"key": "[[q1]]", "question": "Is it live?", "raised_by": "[[c1]]",
                                                  "depends_on": "None"}]})
        self.assertIn("| Q06 | C01 | Is it live? |", self.plain())
        self.assertIn("C01 is still cited by Q06",
                      self.refused("design", {}))

    def test_a_design_claiming_code_needs_it_read(self):
        self.answered()
        component = {"key": "[[c1]]", "name": "API", "kind": "service", "responsibility": "r",
                     "code": "[api](https://git.example/acme/api/tree/abc/api)", "state": "🟩 Live",
                     "evidence": "[[F01]]", "in_the_target": "Unchanged", "boundary": "None"}
        # The problem names the row by its key, not the ID it would have had.
        problems = self.refused(
            "design", {"components": [component]})
        self.assertIn("- components[0]: a component marked", problems)
        self.assertIn("[[c1]] links acme/api: api", problems)

    def test_a_review_round_adds_its_questions(self):
        result = self.submit("review", copy.deepcopy(
            protocol.example("review")), 1)
        self.assertEqual(result["ids"], {"[[q1]]": "Q06"})
        self.assertIn(
            "| Q06 | Review round 1 | Which identity does the index build job use", self.plain())
        self.submit("review", {"raised": []}, 2)
        self.submit("review", {"stopped": "Enough."}, 3)
        self.assertIn(
            "| 1 | Q06 |\n| 2 | No issue raised |\n| 3 | Stopped by the user: Enough. |", self.plain())
        self.assertIn("stopped needs text", self.refused(
            "review", {"stopped": " "}, 4))


if __name__ == "__main__":
    unittest.main()
