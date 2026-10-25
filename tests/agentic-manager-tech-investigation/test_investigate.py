"""Unit tests for skills/agentic-manager-tech-investigation/scripts/investigate.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

Each test starts a new investigation in a temporary output folder and drives
it through next and submit, as the agent does.
"""

import copy
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
sys.path.insert(0, SCRIPTS)
import init_investigation  # noqa: E402
import investigate  # noqa: E402
import ledger  # noqa: E402
import protocol  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, content, temp_output  # noqa: E402

GAP = {"gap": "Billing callers", "established_and_missing": "Callers aren't read", "would_close": "Read access",
       "blocked_by": "No access (billing repository)", "authority": "Code", "owner_and_next_check": "Billing team"}


def answer(claim="A fact.", **outcome):
    """An answer resting on a source the ledger holds, read in full."""
    return {"findings": [{"key": "[[f1]]", "claim": claim, "sources": "[[S02]]", "limits": "Read in full."}],
            "outcome": outcome or {"answered": "[[f1]]"}}


class InvestigateTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=date(2026, 10, 5))
        self.path = Path(self.folder) / INVESTIGATION / "ledger.md"

    def lines(self):
        return self.path.read_text(encoding="utf-8").split("\n")

    def phase(self):
        return investigate.phase_of(INVESTIGATION, self.lines())

    def submit(self, task, data):
        return investigate.submit(INVESTIGATION, task, copy.deepcopy(data))

    def research(self):
        """Work every question: the first with the example answer, so the
        ledger has sources and findings to cite, which raises a question for
        the user; the second blocked by a gap, which the report cites."""
        self.submit("research:Q01", protocol.example("research"))
        self.submit("scope", {"decisions": [{"question": "[[Q07]]", "name": "The payments gateway",
                                             "answer": "mention only"}]})
        self.submit("research:Q02", {"outcome": {"blocked": {"gap": GAP}}})
        for question in ("Q03", "Q04", "Q05", "Q06"):
            self.submit(f"research:{question}",
                        answer(f"Fact for {question}."))

    def design(self):
        return copy.deepcopy(protocol.example("design"))

    def test_the_phase_follows_the_ledger(self):
        # Each step's submission moves the investigation on, in order: the
        # questions, the design, the review rounds, the report.
        self.assertEqual(self.phase(), "research")
        self.research()
        self.assertEqual(self.phase(), "design")
        self.submit("design", self.design())
        self.assertEqual(self.phase(), "review")
        self.submit("review:1", protocol.example("review"))
        self.assertEqual(self.phase(), "research")
        self.submit("research:Q08", answer("It runs in production."))
        # A new finding makes the design out of date, so it is built again.
        self.assertEqual(self.phase(), "design")
        self.submit("design", investigate.design_rows(self.lines()))
        self.assertEqual(self.phase(), "review")
        self.submit("review:2", {"raised": []})
        self.assertEqual(self.phase(), "write")
        self.submit("write", content())
        self.assertEqual(self.phase(), "finished")

    def test_next_hands_out_questions_and_marks_them_in_progress(self):
        text = investigate.next_tasks(INVESTIGATION)
        self.assertTrue(text.startswith("# Task research:Q01"), text[:80])
        # The other open questions are shown, so a new one doesn't repeat them.
        self.assertIn("## Other open questions", text)
        self.assertIn(
            "- Q03: What target design and decisions do the documents record for Acme Search?", text)
        self.assertNotIn("- Q01:", text)
        self.assertEqual([row[0] for row in ledger.table_rows(
            self.lines(), "queue-in-progress")], ["Q01"])
        # Asked again, it hands out the one in progress, and none of the seeds
        # waiting for it.
        text = investigate.next_tasks(INVESTIGATION, 3)
        self.assertEqual([part.split("\n")[0] for part in text.split(investigate.SEPARATOR)],
                         ["# Task research:Q01"])
        # A question waiting on an open one isn't handed out.
        self.submit("research:Q01", {**answer(), "sources": protocol.example("research")["sources"],
                                     "findings": [{"key": "[[f1]]", "claim": "x", "sources": "[[s2]]", "limits": "y"}],
                                     "new_questions": [{"key": "[[q1]]", "question": "Then?", "raised_by": "[[f1]]",
                                                        "depends_on": "[[Q04]]"}]})
        text = investigate.next_tasks(INVESTIGATION, 9)
        self.assertNotIn("# Task research:Q06", text)
        self.assertIn("# Task research:Q04", text)

    def test_questions_for_the_user_come_first_all_together(self):
        # A question for the user is asked before research goes on, with every
        # other one open, in one task; the user's decision closes it and goes in
        # the Boundary, and an included topic opens research questions.
        data = protocol.example("research")
        data["new_questions"].append({"key": "[[q3]]", "question": "Should the investigation cover billing?",
                                      "raised_by": "[[f2]]", "depends_on": "None", "for": "user"})
        self.submit("research:Q01", data)
        text = investigate.next_tasks(INVESTIGATION, 4)
        self.assertTrue(text.startswith("# Task scope"), text[:80])
        for expected in ("- Q07: Should the investigation cover the payments gateway", "- Q08: Should the "
                         "investigation cover billing? (raised by F02)", "## Decided so far\n\nNone yet.",
                         f"--task scope <<'EOF'"):
            with self.subTest(expected):
                self.assertIn(expected, text)
        self.assertNotIn("# Task answer", text)
        result = self.submit("scope", {"decisions": [
            {"question": "[[Q07]]", "name": "The payments gateway",
                "answer": "mention only"},
            {"question": "[[Q08]]", "name": "Billing", "answer": "include"}],
            "new_questions": [{"key": "[[q1]]", "question": "How does search reach billing?", "raised_by": "[[Q08]]",
                               "depends_on": "None"}]})
        self.assertEqual(result["ids"], {"[[q1]]": "Q09"})
        text = self.path.read_text(encoding="utf-8")
        self.assertIn(
            "## Boundary\n\n- The payments gateway: mention only.\n- Billing: include.\n", text)
        completed = {row[0]: row[-1]
                     for row in ledger.table_rows(self.lines(), "queue-completed")}
        self.assertEqual(completed["Q08"], "Decided by the user: include")
        self.assertTrue(investigate.next_tasks(
            INVESTIGATION).startswith("# Task research:Q02"))
        # The research task shows what the user decided.
        self.assertIn("## The scope the user decided so far\n\n- The payments gateway: mention only.",
                      investigate.next_tasks(INVESTIGATION))

    def test_a_task_carries_what_it_needs(self):
        # The API file read only in part, so the task flags it.
        data = protocol.example("research")
        data["sources"][0]["coverage"] = "partial: routes, lines 1-200 of 900"
        data["findings"][0]["limits"] += " [[s1]]: the unread lines hold admin routes."
        self.submit("research:Q01", {**data, "new_questions": [
            {"key": "[[q1]]", "question": "Which job builds the index?", "raised_by": "[[f1]]", "depends_on": "None"}]})
        self.submit("research:Q02", answer())
        for question in ("Q03", "Q04", "Q05"):
            investigate.next_tasks(INVESTIGATION)
            self.submit(f"research:{question}", answer())
        text = investigate.next_tasks(INVESTIGATION)
        for expected in ("# Task research:Q06", "Q06: Which job builds the index?", "Raised by: F01",
                         "It builds on these findings:\n- F01: The search API answers /search",
                         "- S01: code; [api server.py](https://github.com/acme/api/blob/1a2b3c4/server.py); "
                         "1a2b3c4; coverage: partial", "(read in part: a finding citing it says in limits, citing it, why the rest can't change the claim)",
                         "### Reading the tracker",
                         f"python3 {os.path.join(SCRIPTS, 'tickets.py')}",
                         f"submit --investigation {INVESTIGATION} --task research:Q06 <<'EOF'"):
            with self.subTest(expected):
                self.assertIn(expected, text)
        self.assertNotIn("{{", text)

    def test_submit_takes_only_a_task_handed_out_now(self):
        # name: (task, the refusal)
        cases = [("a later step", "design", "design isn't a task now; the task now is research:Q01"),
                 ("asking with no question for the user",
                  "scope", "scope isn't a task now"),
                 ("a question not in the queue", "research:Q10", "Q10 isn't an open research question")]
        for name, task, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                self.submit(task, answer())

    def test_a_question_can_be_answered_out_of_turn_while_open(self):
        # A subagent's answer may come back after another's.
        investigate.next_tasks(INVESTIGATION, 2)
        self.submit("research:Q02", {"outcome": {"blocked": {"gap": GAP}}})
        self.assertEqual([row[0] for row in ledger.table_rows(
            self.lines(), "queue-blocked")], ["Q02"])

    def test_the_design_task_shows_the_scope_decided(self):
        self.research()
        text = investigate.next_tasks(INVESTIGATION)
        self.assertTrue(text.startswith("# Task design"))
        self.assertIn(
            "## The scope the user decided\n\n- The payments gateway: mention only.", text)

    def test_the_review_asks_the_user_after_three_rounds(self):
        self.research()
        self.submit("design", self.design())
        for number in (1, 2, 3):
            self.assertNotIn("ask whether to go on",
                             investigate.next_tasks(INVESTIGATION))
            self.submit(f"review:{number}", {"raised": [{"key": "[[q1]]", "question": f"Round {number}?",
                                                         "depends_on": "None"}]})
            self.submit(f"research:Q{7 + number:02d}",
                        answer(f"Round {number}."))
            self.submit("design", investigate.design_rows(self.lines()))
        text = investigate.next_tasks(INVESTIGATION)
        self.assertIn("# Task review:4", text)
        self.assertIn("ask whether to go on", text)
        self.assertIn(
            'submit what they said: {"stopped": "<what they said>"}', text)
        self.assertIn(
            "show the user what each of the 3 rounds so far raised", text)
        self.assertIn(
            "- Round 1 raised: Q08\n- Round 2 raised: Q09\n- Round 3 raised: Q10", text)

    def test_the_report_is_written_until_it_passes(self):
        self.research()
        self.submit("design", self.design())
        self.submit("review:1", {"raised": []})
        bad = content()
        bad["purpose"] = ["No ledger link."]
        with self.assertRaisesRegex(SystemExit, "purpose paragraph 1: needs a ledger link"):
            self.submit("write", bad)
        # The write task lists what is wrong with the text submitted.
        text = investigate.next_tasks(INVESTIGATION)
        self.assertIn(
            "## Problems with the last text submitted\n\n- purpose paragraph 1: needs a ledger link", text)
        self.assertIn("## The brief", text)
        result = self.submit("write", content())
        self.assertTrue(result["ok"])
        text = investigate.next_tasks(INVESTIGATION)
        self.assertTrue(text.startswith("# Task finished"))
        self.assertIn(result["path"], text)
        with self.assertRaisesRegex(SystemExit, "finished"):
            self.submit("finished", {})

    def test_the_ledger_is_locked_while_a_command_uses_it(self):
        # Subagents submit at once: each waits for the lock, so none writes
        # over another's answer.
        import fcntl
        lock = investigate.lock_path(INVESTIGATION)
        with investigate.locked(INVESTIGATION):
            with open(lock, "a") as other:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with open(lock, "a") as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_a_report_failing_its_final_check_keeps_its_errors(self):
        # The next write task lists why.
        self.research()
        self.submit("design", self.design())
        self.submit("review:1", {"raised": []})
        stray = Path(self.folder) / INVESTIGATION / "notes.md"
        stray.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "notes.md"):
            self.submit("write", content())
        self.assertIn("notes.md", investigate.next_tasks(
            INVESTIGATION).split("## The brief")[0])
        # Once its cause is gone, the report kept passes, with nothing to resubmit.
        stray.unlink()
        self.assertTrue(investigate.next_tasks(
            INVESTIGATION).startswith("# Task finished"))

    def test_a_ledger_warning_is_reported_once(self):
        # A design row's link dropped on a later round is left unused, which
        # the final check warns about; the report's submission says it once.
        self.research()
        design = self.design()
        design["boundaries"][0]["name"] = "[Production cluster](https://example.com/cluster)"
        self.submit("design", design)
        self.submit("review:1", protocol.example("review"))
        self.submit("research:Q08", answer("It runs in production."))
        design["boundaries"][0]["name"] = "Production cluster"
        self.submit("design", design)
        self.submit("review:2", {"raised": []})
        warnings = self.submit("write", content())["warnings"]
        self.assertTrue(any("never used" in w for w in warnings), warnings)
        self.assertEqual(len(warnings), len(set(warnings)), warnings)

    def test_the_commands_name_the_script_as_it_was_run(self):
        # The pre-approved path is the one the agent ran, a symlink included.
        with mock.patch.object(sys, "argv", ["/skills/x/scripts/investigate.py"]):
            self.assertEqual(investigate.call(),
                             "python3 /skills/x/scripts/investigate.py")
            values = investigate.fills(INVESTIGATION)
            self.assertEqual((values["scripts"], values["lib"]),
                             ("/skills/x/scripts", "/skills/x/../agentic-manager-utils-lib/agentic_manager"))


if __name__ == "__main__":
    unittest.main()
