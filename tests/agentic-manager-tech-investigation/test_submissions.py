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
from common import ID_LETTERS  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, temp_output  # noqa: E402

GAP = {"gap": "Billing callers", "established_and_missing": "The API is merged; its callers aren't read",
       "would_close": "Read access", "blocked_by": "No access (billing repository)", "authority": "Code",
       "owner_and_next_check": "Billing team"}


def finding(key="[[f1]]", claim="Search reads the index.", sources="[[S01]]", **more):
    """A finding as a submission gives it."""
    return {"key": key, "claim": claim, "sources": sources, "limits": "Read in full.", **more}


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
                                     "revision": "abc", "coverage": "full"}])
        data.setdefault("findings", [finding(sources="[[s1]]")])
        data.setdefault("outcome", {"answered": "[[f1]]"})
        return self.submit("research", question, data)

    def test_the_users_decisions_close_their_questions_and_form_the_boundary(self):
        self.submit("research", "Q01", copy.deepcopy(
            protocol.example("research")))
        self.assertIn(
            "| Q07 | F01 | For the user: Should the investigation cover the payments gateway", self.plain())
        # name: (the decisions, a problem they list)
        cases = [("a question not handed out", [{"question": "[[Q02]]", "name": "x", "answer": "include"}],
                  "decisions[0].question is one of the questions handed out: [[Q07]]"),
                 ("an answer not allowed", [{"question": "[[Q07]]", "name": "x", "answer": "maybe"}],
                  "decisions[0].answer is one of: include, mention only, exclude"),
                 ("a question decided twice", [{"question": "[[Q07]]", "name": "x", "answer": "exclude"}] * 2,
                  "decisions[1].question [[Q07]] is decided twice"),
                 ("no name", [{"question": "[[Q07]]", "answer": "exclude"}], "decisions[0].name needs text")]
        for name, decisions, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused(
                    "scope", {"decisions": decisions}, ["Q07"]))
        self.submit("scope", {"decisions": [{"question": "[[Q07]]", "name": "The payments gateway",
                                             "answer": "exclude"}]}, ["Q07"])
        self.assertIn(
            "## Boundary\n\n- The payments gateway: exclude.\n\n## Independent reviews", self.text())
        self.assertIn("| For the user: Should the investigation cover the payments gateway the search API calls for "
                      "paid results? | None | Decided by the user: exclude |", self.plain())
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
        # Its partial read is said in the finding's limits, citing the source.
        self.assertIn("S01: the unread lines hold admin routes", self.plain())
        self.assertEqual(check_report.check_ledger(self.path)[0], [])

    def test_a_source_read_again_keeps_its_id(self):
        self.answered()
        self.answered("Q02", sources=[{"key": "[[s1]]", "kind": "code", "reference": "[the api](https://example.com/api)",
                                       "revision": "abc", "coverage": "full: re-read"}],
                      findings=[finding(claim="Another fact.", sources="[[s1]]")])
        self.assertEqual(self.rows("sources"), ["S01"])
        self.assertIn("| full: re-read | F01, F02 |", self.plain())

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
        # name: (the findings, a problem they list)
        cases = [("a bare key where a field cites", [finding(sources="s1")],
                  "write each reference in double brackets, such as [[s1]]"),
                 ("a bare ID where a field cites", [finding(sources="S01")],
                  "write each reference in double brackets, such as [[S01]]"),
                 ("a key declared bare", [
                  finding("f1")], "findings[0].key is [[f1]]"),
                 ("a key nothing declares", [
                  finding(limits="See [[f9]].")], "[[f9]] is no key of this submission"),
                 ("an ID the ledger doesn't hold", [finding(sources="[[S09]]")], "cites S09, which the ledger")]
        for name, findings, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused("research", "Q02", {"findings": findings,
                                                                         "outcome": {"answered": "[[f1]]"}}))

    def test_a_partial_read_is_explained_in_the_limits(self):
        # A finding citing a source read only in part cites it again in its
        # limits, saying why the unread part can't change the claim.
        partial = [{"key": "[[s1]]", "kind": "code", "reference": "[api](https://example.com/api)", "revision": "abc",
                    "coverage": "partial: lines 1-80"}]
        problems = self.refused("research", "Q01", {"sources": partial, "findings": [finding(sources="[[s1]]")],
                                                    "outcome": {"answered": "[[f1]]"}})
        self.assertIn("findings[0]: cites [[s1]], read only in part: read the rest, or say in limits, citing [[s1]], "
                      "why the unread part can't change the claim", problems)
        self.submit("research", "Q01", {"sources": partial, "findings": [finding(
            sources="[[s1]] (lines 1-40)", limits="Routes read. [[s1]]: the unread lines are admin routes.")],
            "outcome": {"answered": "[[f1]]"}})
        self.assertIn(
            "| Routes read. S01: the unread lines are admin routes. |", self.plain())
        # The field that once held the reason is refused.
        self.assertIn("has no field partial_read", self.refused("research", "Q02", {
            "findings": [finding(partial_read="x")], "outcome": {"answered": "[[f1]]"}}))

    def test_every_problem_is_listed_by_field_and_nothing_is_written(self):
        data = {"sources": [{"key": "[[s1]]", "kind": "source_control", "reference": "[api](https://example.com/api)",
                             "revision": "abc", "coverage": "skimmed"}],
                "findings": [finding(sources="[[s1]], [[s9]]"), finding("[[f1]]", "Again."),
                             finding("x2", "word " * 151, sources="[[s1]]")],
                "new_questions": [{"key": "[[q1]]", "question": "Why?", "raised_by": "[[f1]]", "depends_on": "[[Q99]]"}],
                "outcome": {"answered": "[[f1]]"}, "notes": "x"}
        problems = self.refused("research", "Q01", data)
        for expected in ("the submission has no field notes", "sources[0]: sources [[s1]]: Kind starts with",
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
        # Closing it records what it leaves out beside the user's decisions, so
        # every later task sees it.
        self.submit("research", "Q01", copy.deepcopy(
            protocol.example("research")))
        self.submit("scope", {"decisions": [{"question": "[[Q07]]", "name": "The payments gateway",
                                             "answer": "mention only"}]}, ["Q07"])
        self.submit("research", "Q02", {"outcome": {"outside_scope": {"decided_in": "[[Q07]]",
                                                                      "name": "The gateway's retry queue"}}})
        completed = {row[0]: row[-1]
                     for row in ledger.table_rows(self.text().split("\n"), "queue-completed")}
        self.assertEqual(
            completed["Q02"], "Outside the scope the user decided in [Q07](#q07)")
        self.assertIn("- The payments gateway: mention only.\n- The gateway's retry queue, under [Q07](#q07): "
                      "mention only.", self.text())
        self.assertEqual(check_report.check_ledger(self.path)[0], [])
        # name: (the outcome, a problem it lists)
        cases = [("a decision the user included", {"decided_in": "[[Q01]]", "name": "x"}, "is no question the user"),
                 ("a question not in the ledger", {
                  "decided_in": "[[Q09]]", "name": "x"}, "is no question the user"),
                 ("no name", {
                  "decided_in": "[[Q07]]"}, 'outcome.outside_scope is {"decided_in"'),
                 ("only the question", "[[Q07]]", 'outcome.outside_scope is {"decided_in"')]
        for name, given, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.refused(
                    "research", "Q03", {"outcome": {"outside_scope": given}}))

    def test_a_blocked_question_blocks_those_that_need_it(self):
        self.answered(findings=[finding(sources="[[s1]]")],
                      new_questions=[{"key": "[[q1]]", "question": "Next?", "raised_by": "[[f1]]", "depends_on": "[[Q02]]"}])
        result = self.submit(
            "research", "Q02", {"outcome": {"blocked": {"gap": GAP}}})
        self.assertEqual(result["blocked"], ["Q06"])
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
        self.answered()
        self.submit("research", "Q02", {"outcome": {"blocked": {"gap": GAP}}})
        design = copy.deepcopy(protocol.example("design"))
        design["components"][0]["code"] = "None"
        design["components"][0]["status"] = "🟨 Planned"
        design["connections"][0]["state"] = "🟨 Planned"
        design["components"][1]["next_steps"] = "Unchanged"
        result = self.submit("design", design, (1, 1, 0))
        self.assertEqual(result["ids"], {"[[b1]]": "B01", "[[i1]]": "I01", "[[c1]]": "C01", "[[c2]]": "C02", "[[e1]]": "E01",
                                         "[[p1]]": "P01"})
        self.assertEqual(ledger.design_basis(
            self.text().split("\n")), (1, 1, 0))
        # Submitted again with its own IDs, a row is kept; one left out is removed,
        # and a new one takes a number never used.
        current = submissions.design_rows(self.text().split("\n"))
        current["components"] = [current["components"][0], {**current["components"][0], "key": "[[c1]]",
                                                            "name_and_type": "Worker (job)"}]
        current["connections"] = []
        current["flows"] = []
        result = self.submit("design", current, (1, 1, 0))
        self.assertEqual(result["ids"]["[[c1]]"], "C03")
        self.assertEqual(self.rows("components"), ["C01", "C03"])
        self.assertEqual(self.rows("connections"), [])
        self.assertEqual(check_report.check_ledger(self.path)[0], [])

    def test_a_design_row_still_cited_cant_be_left_out(self):
        self.answered()
        component = {"key": "[[c1]]", "name_and_type": "API (service)", "responsibility": "r", "code": "None",
                     "status": "🟨 Planned", "how_much_was_read": "None", "evidence": "[[F01]]", "next_steps": "n",
                     "boundary": "None"}
        self.submit("design", {"components": [component],
                               "new_questions": [{"key": "[[q1]]", "question": "Is it live?", "raised_by": "[[c1]]",
                                                  "depends_on": "None"}]}, (1, 0, 0))
        self.assertIn("| Q06 | C01 | Is it live? |", self.plain())
        self.assertIn("C01 is still cited by Q06",
                      self.refused("design", {}, (1, 0, 0)))

    def test_a_design_claiming_code_needs_it_read(self):
        self.answered()
        component = {"key": "[[c1]]", "name_and_type": "API (service)", "responsibility": "r",
                     "code": "[api](https://git.example/acme/api/tree/abc/api)", "status": "🟩 Implemented",
                     "how_much_was_read": "None", "evidence": "[[F01]]", "next_steps": "n", "boundary": "None"}
        # The problem names the row by its key, not the ID it would have had.
        problems = self.refused(
            "design", {"components": [component]}, (1, 0, 0))
        self.assertIn("- components[0]: a component marked", problems)
        self.assertIn("[[c1]] links acme/api: api", problems)

    def test_a_review_round_adds_its_questions(self):
        result = self.submit("review", copy.deepcopy(
            protocol.example("review")), 1)
        self.assertEqual(result["ids"], {"[[q1]]": "Q06"})
        self.assertIn(
            "| Q06 | Review round 1 | Does the index build job run in production", self.plain())
        self.submit("review", {"raised": []}, 2)
        self.submit("review", {"stopped": "Enough."}, 3)
        self.assertIn(
            "| 1 | Q06 |\n| 2 | No issue raised |\n| 3 | Stopped by the user: Enough. |", self.plain())
        self.assertIn("stopped needs text", self.refused(
            "review", {"stopped": " "}, 4))


if __name__ == "__main__":
    unittest.main()
