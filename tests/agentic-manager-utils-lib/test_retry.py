"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/retry.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import retry  # noqa: E402


class Failed(Exception):
    """A failure that is passing or final, as `passing` says."""

    def __init__(self, passing):
        super().__init__("passing" if passing else "final")
        self.passing = passing


class RetriedTest(unittest.TestCase):
    def test_retried(self):
        # A passing failure is tried again after each of RETRY_WAITS, then
        # raised; any other failure, a rate limit included, is final at once.
        # name: (what each try does, an answer or whether its failure is
        # passing, the expected answer or None for the last failure raised,
        # the waits)
        passing, final = True, False
        cases = [
            ("answers at once", ["ok"], "ok", []),
            ("passing, then answers", [passing, passing, "ok"], "ok", [1, 3]),
            ("passing every time", [passing] * 4, None, [1, 3, 9]),
            ("final at once", [final], None, []),
            ("passing, then final", [passing, final], None, [1]),
        ]
        for name, tries, expected, waits in cases:
            with self.subTest(name), mock.patch.object(retry.time, "sleep") as sleep, \
                    mock.patch.object(retry, "RETRY_WAITS", (1, 3, 9)), \
                    contextlib.redirect_stderr(io.StringIO()) as said:
                queue = list(tries)

                def attempt():
                    outcome = queue.pop(0)
                    if outcome == "ok":
                        return outcome
                    raise Failed(outcome)

                def call():
                    return retry.retried(attempt, lambda error: error.passing, lambda error: f"failed as {error}")
                if expected is None:
                    with self.assertRaises(Failed):
                        call()
                else:
                    self.assertEqual(call(), expected)
                self.assertEqual(queue, [])
                self.assertEqual(
                    [c.args[0] for c in sleep.call_args_list], waits)
                # Each wait is said, in the client's words, so a run that
                # recovered still shows the service struggled.
                self.assertEqual(said.getvalue(), "".join(
                    f"failed as passing, trying again in {wait} s\n" for wait in waits))


if __name__ == "__main__":
    unittest.main()
