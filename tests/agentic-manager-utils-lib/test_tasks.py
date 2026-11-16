"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/tasks.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import tasks  # noqa: E402


class TasksTest(unittest.TestCase):
    def test_write_task(self):
        # The folder is created, the file ends with one newline, and a
        # rewrite replaces it.
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "Q01")
            path = os.path.join(folder, "task.md")
            for text in ("# Task research:Q01\n\nRead.", "# Task research:Q01\n\nRead again.\n\n"):
                with self.subTest(text):
                    self.assertEqual(tasks.write_task(folder, "research:Q01", text),
                                     f"Task research:Q01: {path}")
                    with open(path, encoding="utf-8") as f:
                        self.assertEqual(f.read(), text.rstrip("\n") + "\n")

    def test_submit_section(self):
        self.assertEqual(
            tasks.submit_section("python3 x.py submit --task merge",
                                 '{"items": [...]}'),
            "## Submit\n\nSubmit your answer, as JSON in a quoted here-document:\n\n```bash\n"
            "python3 x.py submit --task merge <<'END_OF_INPUT'\n{\"items\": [...]}\nEND_OF_INPUT\n```\n\n"
            "If the script refuses it, fix every problem it names and submit again, until it is accepted.")


if __name__ == "__main__":
    unittest.main()
