"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/init_prep.py.
Run as a script, with set_identities.py and check_prep.py after it, it has end-to-end tests in
test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The config's path is patched to the test's own config, in a temporary folder.
"""

import json
import os
import sys
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import init_prep  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import temp_output  # noqa: E402

TODAY = date(2026, 11, 10)
START, END = date(2026, 8, 10), TODAY


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_new_prep_then_a_rerun_replaces_it(self):
        # A new prep holds only its request; running it again the same day
        # starts from scratch, but leaves the folders of other days.
        result = init_prep.init("  José   Núñez ", START, END, today=TODAY)
        path = os.path.join(self.folder, "Jose-Nunez_26-11-10")
        request = {"person": "José Núñez",
                   "start": "2026-08-10", "end": "2026-11-10"}
        self.assertEqual(result, {"folder": self.folder, "temporary": False, "prep": "Jose-Nunez_26-11-10",
                                  "prep_dir": path, "replaced": False, "request": request,
                                  "shown": "10/08/2026 to 10/11/2026"})
        self.assertEqual(os.listdir(path), ["request.json"])
        with open(os.path.join(path, "request.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), request)
        with open(os.path.join(path, "left-over.md"), "w", encoding="utf-8") as f:
            f.write("from an earlier run")
        earlier = os.path.join(self.folder, "Jose-Nunez_26-11-09")
        os.makedirs(earlier)
        self.assertTrue(init_prep.init(
            "José Núñez", START, END, today=TODAY)["replaced"])
        self.assertEqual(os.listdir(path), ["request.json"])
        self.assertTrue(os.path.isdir(earlier))

    def test_refuses_a_request_it_cant_prepare(self):
        # The request's rules are common.request_problems(), tested in
        # test_common.py: a request that breaks one writes nothing.
        for person, start, end in (("  ", START, END), ("Jane Doe", START, date(2026, 12, 31))):
            with self.subTest(person=person, end=end), self.assertRaises(SystemExit):
                init_prep.init(person, start, end, today=TODAY)
        self.assertFalse(os.path.exists(self.folder))


if __name__ == "__main__":
    unittest.main()
