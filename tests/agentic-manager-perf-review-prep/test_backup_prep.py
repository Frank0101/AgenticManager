"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/backup_prep.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import backup_prep  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, temp_output, write_prep  # noqa: E402


class BackupPrepTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder)
        self.notes = os.path.join(self.folder, PREP, "notes.json")

    def write_notes(self, text):
        with open(self.notes, "w", encoding="utf-8") as f:
            f.write(text)

    def read_notes(self):
        with open(self.notes, encoding="utf-8") as f:
            return f.read()

    def test_keeps_the_first_version_and_puts_it_back(self):
        # The first save copies the prep as the skill made it; a save after
        # a change keeps that first copy; restore puts the whole prep back
        # as it was, a file added since gone too.
        first = self.read_notes()
        self.assertTrue(backup_prep.save(PREP)["saved"])
        self.write_notes("changed once")
        self.assertFalse(backup_prep.save(PREP)["saved"])
        self.write_notes("changed twice")
        extra = os.path.join(self.folder, PREP, "extra.json")
        with open(extra, "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(backup_prep.restore(PREP), {
                         "prep_dir": os.path.join(self.folder, PREP)})
        self.assertEqual(self.read_notes(), first)
        self.assertFalse(os.path.exists(extra))

    def test_restore_without_a_save(self):
        # With nothing saved there is nothing to go back to: the prep is
        # left as it is.
        with self.assertRaises(SystemExit) as raised:
            backup_prep.restore(PREP)
        self.assertIn("run save before a change", str(raised.exception))
        self.assertTrue(os.path.exists(self.notes))


if __name__ == "__main__":
    unittest.main()
