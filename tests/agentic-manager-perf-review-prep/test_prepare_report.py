"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/prepare_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import prepare_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import EARLIER_WORK_BRIEF, OBSERVATIONS_BRIEF, DATA, PREP, STEP_CHANGE_BRIEF, WORK_IMPACT_BRIEF, temp_output, write_prep  # noqa: E402


class PrepareReportTest(unittest.TestCase):
    def test_prepare(self):
        # data.json and the four briefs, then a task for each: its protocol
        # filled in, the person, its own brief's path and the command that
        # records what it writes, with the shape of its answer.
        folder = temp_output(self)
        write_prep(folder, data=None, observations_brief=None, observations_content=None,
                   step_change_brief=None, step_change_content=None, work_impact_brief=None,
                   work_impact_content=None, earlier_work_brief=None, earlier_work_content=None, report=False)
        prepared = prepare_report.prepare(PREP)
        brief, step_change_brief, work_brief, earlier_brief = prepared["briefs"]
        self.assertEqual((common.read_json(os.path.join(folder, PREP, "data.json")), common.read_json(brief),
                          common.read_json(
                              step_change_brief), common.read_json(work_brief),
                          common.read_json(earlier_brief)),
                         (DATA, OBSERVATIONS_BRIEF, STEP_CHANGE_BRIEF, WORK_IMPACT_BRIEF, EARLIER_WORK_BRIEF))
        read_alone = "## What to read\n\nThe brief, at the path below, holds all you need; read nothing else."
        # name: (task, in its text, not in its text)
        cases = [("work-impact", [f"about {common.WORDS['work_impact_line']} words for the impact line and "
                                  f"{common.WORDS['work_impact']} for the paragraph", "jira_ticket.py --key",
                                  "extract_saved.py", '{"initiatives": [{"title": "..."', work_brief,
                                  f"set_work_impact.py --prep {PREP} <<'END_OF_INPUT'"],
                  [read_alone, brief + "\n"]),
                 ("earlier-work", [f"up to {common.MAX_EARLIER_BULLETS} bullets",
                                   f"about {common.WORDS['earlier_work']} words", '{"bullets": ["..."',
                                   earlier_brief, f"set_earlier_work.py --prep {PREP} <<'END_OF_INPUT'"],
                  [brief + "\n", "jira_ticket.py"]),
                 ("observations", [f"about {common.WORDS['value']} words a value",
                                   f"about {common.WORDS['context']} words", "## How to write the context",
                                   common.OBSERVATIONS_SHAPE, brief, read_alone,
                                   f"set_observations.py --prep {PREP} <<'END_OF_INPUT'"],
                  ["step change", step_change_brief]),
                 ("step-change", [f"about {common.WORDS['step_change']} words",
                                  "## How to write the rows", '{"summary": "...", "rows": [{"previous_point": "P-I1"',
                                  step_change_brief, read_alone, f"set_step_change.py --prep {PREP} <<'END_OF_INPUT'"],
                  ["## How to write the context", brief + "\n"])]
        self.assertEqual([line.split(":", 1)[0] for line in prepared["tasks"]],
                         [f"Task {name}" for name, *_ in cases])
        for (name, present, absent), line in zip(cases, prepared["tasks"]):
            with self.subTest(name):
                with open(line.removeprefix(f"Task {name}: "), encoding="utf-8") as f:
                    task = f.read()
                self.assertNotIn("{{", task)
                # The sources the points come from, said once.
                shared = ("Other agents read the manager's own feedback on the person, the manager's notes, the "
                          "person's Slack messages and the other feedback the person received in the period")
                # The work before the period reads the previous feedback alone.
                self.assertEqual(task.count(shared), 0 if name ==
                                 "earlier-work" else 1, shared)
                for part in [*present, "## The person\n\nJane Doe"]:
                    self.assertIn(part, task)
                for part in absent:
                    self.assertNotIn(part, task)

    def test_prepare_with_nothing_to_compare(self):
        # With no previous feedback there is nothing to compare or recall:
        # the step change and the work before the period are recorded as
        # null, with no task for them, so no agent is started to write what a
        # script knows.
        empty = {"going_well": [], "to_improve": [], "context": []}
        folder = temp_output(self)
        write_prep(folder, data=None, observations_brief=None, observations_content=None, step_change_brief=None, step_change_content=None,
                   earlier_work_brief=None, earlier_work_content=None, report=False, previous=empty)
        prepared = prepare_report.prepare(PREP)
        self.assertEqual([line.split(":", 1)[0]
                         for line in prepared["tasks"]], ["Task work-impact", "Task observations"])
        for name in (common.STEP_CHANGE_CONTENT, common.EARLIER_WORK_CONTENT):
            self.assertIsNone(common.read_json(
                os.path.join(folder, PREP, name)))


if __name__ == "__main__":
    unittest.main()
