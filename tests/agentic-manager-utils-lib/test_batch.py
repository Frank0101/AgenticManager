"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/batch.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import sys
import threading
import time
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

    def test_workers(self):
        # Four calls at a time: Jira drops connections and GitHub discourages
        # concurrent requests under more.
        self.assertEqual(batch.WORKERS, 4)


class Failed(Exception):
    pass


class GatherTest(unittest.TestCase):
    def test_gather(self):
        # The answers in the order of the items, whatever order the calls end
        # in; the first call to fail stops the rest, its error raised, and
        # with one worker no call starts after it. A SystemExit, as the Jira
        # client raises, stops it the same way.
        def call(item):
            if item == "fail":
                raise Failed(item)
            if item == "exit":
                raise SystemExit(item)
            # The first ends last, so an answer in order isn't one in time.
            time.sleep(0.02 if item == "a" else 0)
            return item.upper()
        # name: (workers, items, the answers, or the error raised, the calls
        # made, or None when calls running beside the failure may end)
        cases = [("in order", 4, ["a", "b", "c"], ["A", "B", "C"], None),
                 ("one at a time", 1, ["a", "b"], ["A", "B"], ["a", "b"]),
                 ("none", 4, [], [], []),
                 ("any iterable", 4, iter("ab"), ["A", "B"], None),
                 ("a failure", 4, ["a", "fail", "c"], Failed, None),
                 ("no call after a failure", 1, [
                  "a", "fail", "c", "d"], Failed, ["a", "fail"]),
                 ("Jira's exit", 1, ["a", "exit", "c"], SystemExit, ["a", "exit"])]
        for name, workers, items, expected, made in cases:
            with self.subTest(name):
                calls = []

                def recorded(item):
                    calls.append(item)
                    return call(item)
                if isinstance(expected, list):
                    self.assertEqual(batch.gather(
                        items, recorded, workers), expected)
                else:
                    with self.assertRaises(expected):
                        batch.gather(items, recorded, workers)
                if made is not None:
                    self.assertEqual(calls, made)

    def test_at_most_workers_at_once(self):
        # At most `workers` calls at once, WORKERS by default.
        lock, running, most = threading.Lock(), [0], [0]

        def call(item):
            with lock:
                running[0] += 1
                most[0] = max(most[0], running[0])
            time.sleep(0.01)
            with lock:
                running[0] -= 1
            return item
        for workers in (1, 2, None):
            with self.subTest(workers):
                most[0] = 0
                items = list(range(12))
                answers = batch.gather(items, call) if workers is None else batch.gather(
                    items, call, workers)
                self.assertEqual(answers, items)
                self.assertLessEqual(most[0], workers or batch.WORKERS)


if __name__ == "__main__":
    unittest.main()
