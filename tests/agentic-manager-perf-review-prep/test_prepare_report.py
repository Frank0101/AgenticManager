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
from prep_fixture import BRIEF, DATA, PREP, temp_output, write_prep  # noqa: E402


class PrepareReportTest(unittest.TestCase):
    def test_prepare(self):
        # data.json and the brief, then the summaries' task: its protocol
        # filled in, the person, the brief's path and the command that
        # records the summaries.
        folder = temp_output(self)
        write_prep(folder, data=None, brief=None, content=None, report=False)
        prepared = prepare_report.prepare(PREP)
        self.assertEqual((common.read_json(os.path.join(folder, PREP, "data.json")),
                          common.read_json(prepared["brief"])), (DATA, BRIEF))
        with open(prepared["task"].removeprefix("Task observations: "), encoding="utf-8") as f:
            task = f.read()
        self.assertNotIn("{{", task)
        for part in (f"about {common.OBSERVATIONS_WORDS['going_well']} words", f"about {common.OBSERVATIONS_WORDS['context']} words",
                     "## The person\n\nJane Doe", prepared[
                         "brief"],
                     f"set_content.py --prep {PREP} <<'END_OF_INPUT'"):
            self.assertIn(part, task)


if __name__ == "__main__":
    unittest.main()
