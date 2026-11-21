"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_earlier_work.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import re
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import set_earlier_work  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DATA, EARLIER_WORK_CONTENT, PREP, temp_output, write_prep  # noqa: E402


class SetEarlierWorkTest(unittest.TestCase):
    def test_set_earlier_work(self):
        # name: (data.json's previous feedback, the value, the problem
        # expected, or None when it is written): one to five bullets, each
        # not too long and naming no id, with previous feedback; null with
        # none; refused, writing nothing, with every problem and the input.
        long = " ".join(
            ["word"] * (common.MAX_WORDS["earlier_work"] + 1))
        cases = [("as written", DATA["previous"], EARLIER_WORK_CONTENT, None),
                 ("null with no previous feedback", None, None, None),
                 ("null with previous feedback",
                  DATA["previous"], None, "must be {"),
                 ("bullets with no previous feedback", None,
                  EARLIER_WORK_CONTENT, "must be null"),
                 ("no bullet", DATA["previous"], {
                  "bullets": []}, "has 0 bullets"),
                 ("six bullets", DATA["previous"], {
                  "bullets": ["Jane built it."] * 6}, "has 6 bullets"),
                 ("a bullet too long", DATA["previous"], {"bullets": [long]},
                  f"cut it to about {common.WORDS['earlier_work']}"),
                 ("an id in a bullet", DATA["previous"], {
                  "bullets": ["Jane built it, as P-G1 says."]}, "names P-G1"),
                 ("an empty bullet", DATA["previous"], {"bullets": [" "]}, "bullet 1 is empty")]
        for name, previous, value, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, data={**DATA, "previous": previous},
                           earlier_work_content=None, report=False)
                path = os.path.join(folder, PREP, common.EARLIER_WORK_CONTENT)
                if expected is None:
                    self.assertEqual(common.read_json(
                        set_earlier_work.set_earlier_work(PREP, value)), value)
                    continue
                with self.assertRaisesRegex(SystemExit, f"{re.escape(expected)}(.|\n)*"
                                            "python3 set_earlier_work.py --prep(.|\n)*END_OF_INPUT"):
                    set_earlier_work.set_earlier_work(PREP, value)
                self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
