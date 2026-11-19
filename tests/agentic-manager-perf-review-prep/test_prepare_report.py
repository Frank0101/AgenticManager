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
from prep_fixture import OBSERVATIONS_BRIEF, DATA, PREP, STEP_CHANGE_BRIEF, temp_output, write_prep  # noqa: E402


class PrepareReportTest(unittest.TestCase):
    def test_prepare(self):
        # data.json and the two briefs, then a task for each: its protocol
        # filled in, the person, its own brief's path and the command that
        # records what it writes, with the shape of its answer.
        folder = temp_output(self)
        write_prep(folder, data=None, observations_brief=None, observations_content=None,
                   step_change_brief=None, step_change_content=None, report=False)
        prepared = prepare_report.prepare(PREP)
        brief, step_change_brief = prepared["briefs"]
        self.assertEqual((common.read_json(os.path.join(folder, PREP, "data.json")), common.read_json(brief),
                          common.read_json(step_change_brief)),
                         (DATA, OBSERVATIONS_BRIEF, STEP_CHANGE_BRIEF))
        # name: (task, in its text, not in its text)
        cases = [("observations", [f"about {common.OBSERVATIONS_WORDS['going_well']} words",
                                   f"about {common.OBSERVATIONS_WORDS['context']} words", "## How to write the context",
                                   '{"going_well": "...", "to_improve": "...", "context": "..."}', brief,
                                   f"set_observations.py --prep {PREP} <<'END_OF_INPUT'"],
                  ["step change", step_change_brief]),
                 ("step-change", [f"about {common.OBSERVATIONS_WORDS['step_change']} words",
                                  "## How to write the rows", '{"summary": "...", "rows": [{"previous_point": "P-I1"',
                                  step_change_brief, f"set_step_change.py --prep {PREP} <<'END_OF_INPUT'"],
                  ["## How to write the context", brief + "\n"])]
        self.assertEqual([line.split(":", 1)[0] for line in prepared["tasks"]],
                         [f"Task {name}" for name, *_ in cases])
        for (name, present, absent), line in zip(cases, prepared["tasks"]):
            with self.subTest(name):
                with open(line.removeprefix(f"Task {name}: "), encoding="utf-8") as f:
                    task = f.read()
                self.assertNotIn("{{", task)
                # The opening both share, said once: the sources, now with the
                # manager's own feedback, and the brief to read alone.
                for shared in ("Other agents read the manager's own feedback on the person, the manager's notes, the "
                               "person's Slack messages and the other feedback the person received in the period",
                               "## What to read\n\nThe brief, at the path below, holds all you need; read nothing else."):
                    self.assertEqual(task.count(shared), 1, shared)
                for part in [*present, "## The person\n\nJane Doe"]:
                    self.assertIn(part, task)
                for part in absent:
                    self.assertNotIn(part, task)

    def test_prepare_with_nothing_to_compare(self):
        # With no previous feedback there is nothing to compare: the step
        # change is recorded as null, with no task for it, so no agent is
        # started to write what a script knows.
        empty = {"going_well": [], "to_improve": [], "context": []}
        folder = temp_output(self)
        write_prep(folder, data=None, observations_brief=None, observations_content=None, step_change_brief=None, step_change_content=None,
                   report=False, previous=empty)
        prepared = prepare_report.prepare(PREP)
        self.assertEqual([line.split(":", 1)[0]
                         for line in prepared["tasks"]], ["Task observations"])
        self.assertIsNone(common.read_json(
            os.path.join(folder, PREP, common.STEP_CHANGE_CONTENT)))


if __name__ == "__main__":
    unittest.main()
