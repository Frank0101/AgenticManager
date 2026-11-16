"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_content.py.
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
import set_content  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import CONTENT, PREP, temp_output, write_prep  # noqa: E402


class SetContentTest(unittest.TestCase):
    def test_set_content(self):
        # Written once it summarises data.json's tables; refused, writing
        # nothing, with every problem.
        folder = temp_output(self)
        write_prep(folder, content=None, report=False)
        with self.assertRaisesRegex(SystemExit, "to_improve is empty"):
            set_content.set_content(PREP, {**CONTENT, "to_improve": ""})
        self.assertFalse(os.path.exists(
            os.path.join(folder, PREP, "content.json")))
        self.assertEqual(common.read_json(
            set_content.set_content(PREP, CONTENT)), CONTENT)


if __name__ == "__main__":
    unittest.main()
