"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/batch.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import sys
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import batch  # noqa: E402


class BatchesTest(unittest.TestCase):
    def test_batches(self):
        # Consecutive lists of at most BATCH_SIZE, in order; nothing for
        # nothing. name: (items, expected)
        cases = [("none", [], []),
                 ("fewer than a batch", [1], [[1]]),
                 ("a full batch", [1, 2], [[1, 2]]),
                 ("a full batch and some", [
                  1, 2, 3, 4, 5], [[1, 2], [3, 4], [5]]),
                 ("any iterable", iter("abc"), [["a", "b"], ["c"]])]
        for name, items, expected in cases:
            with self.subTest(name), mock.patch.object(batch, "BATCH_SIZE", 2):
                self.assertEqual(batch.batches(items), expected)
        self.assertEqual(batch.BATCH_SIZE, 100)


if __name__ == "__main__":
    unittest.main()
