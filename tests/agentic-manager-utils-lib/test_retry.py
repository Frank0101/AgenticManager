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
    """A failure that is passing, final, or a rate limit `rate_wait` asks to
    wait out for `seconds` (None: final)."""

    def __init__(self, kind, seconds=None):
        super().__init__(kind)
        self.kind, self.seconds = kind, seconds


class RetriedTest(unittest.TestCase):
    def test_retried(self):
        # A passing failure is tried again after each of RETRY_WAITS, then
        # raised; a rate limit after the wait rate_wait gives, at most
        # RATE_WAITS_AT_MOST times and never longer than LONGEST_RATE_WAIT,
        # else it is final, as is any other failure, at once.
        # name: (what each try does, "ok" or a Failed, the expected answer or
        # None for the last failure raised, the waits, the rate-limit tries
        # rate_wait was told)
        passing, final = Failed("passing"), Failed("final")
        cap = retry.LONGEST_RATE_WAIT
        cases = [
            ("answers at once", ["ok"], "ok", [], []),
            ("passing, then answers", [
             passing, passing, "ok"], "ok", [1, 3], []),
            ("passing every time", [passing] * 4, None, [1, 3, 9], []),
            ("final at once", [final], None, [], []),
            ("passing, then final", [passing, final], None, [1], []),
            ("rate limit waited out", [Failed("rate", 60), Failed(
                "rate", 120), "ok"], "ok", [60, 120], [0, 1]),
            ("rate limit every time", [
             Failed("rate", 2)] * 4, None, [2, 2, 2], [0, 1, 2]),
            ("rate limit not to wait out", [Failed("rate")], None, [], [0]),
            ("rate limit at the cap", [
             Failed("rate", cap), "ok"], "ok", [cap], [0]),
            ("rate limit over the cap", [
             Failed("rate", cap + 1)], None, [], [0]),
            ("rate limit and passing, apart", [passing, Failed(
                "rate", 5), passing, "ok"], "ok", [1, 5, 3], [0]),
        ]
        for name, tries, expected, waits, told in cases:
            with self.subTest(name), mock.patch.object(retry.time, "sleep") as sleep, \
                    contextlib.redirect_stderr(io.StringIO()) as said:
                queue, asked = list(tries), []

                def attempt():
                    outcome = queue.pop(0)
                    if outcome == "ok":
                        return outcome
                    raise outcome

                def rate_wait(error, tries):
                    if error.kind != "rate":
                        return None
                    asked.append(tries)
                    return error.seconds

                def call():
                    return retry.retried(attempt, lambda error: error.kind == "passing",
                                         lambda error: f"failed as {error}", rate_wait)
                if expected is None:
                    with self.assertRaises(Failed):
                        call()
                else:
                    self.assertEqual(call(), expected)
                self.assertEqual(queue, [])
                self.assertEqual(
                    [c.args[0] for c in sleep.call_args_list], waits)
                self.assertEqual(asked, told)
                # Each wait is said, in the client's words, so a run that
                # recovered still shows the service struggled.
                failures = [t for t in tries if t != "ok"]
                waited = failures if expected else failures[:-1]
                self.assertEqual(said.getvalue(), "".join(
                    f"failed as {error}, trying again in {wait} s\n" for error, wait in zip(waited, waits)))
        self.assertEqual(retry.RETRY_WAITS, (1, 3, 9))

    def test_without_rate_wait(self):
        # A client that gives no rate_wait has every failure but a passing
        # one final at once.
        def attempt():
            raise Failed("rate", 1)
        with mock.patch.object(retry.time, "sleep") as sleep, self.assertRaises(Failed):
            retry.retried(attempt, lambda error: False, str)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
