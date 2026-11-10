"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/check_prep.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_prep  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import FEEDBACK, IDENTITIES, ORIENTATION, PREP, REQUEST, REVIEW, temp_output, write_prep  # noqa: E402

TODAY = date(2026, 11, 10)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_a_prep_the_scripts_wrote_passes(self):
        write_prep(self.folder)
        # Names starting with a dot, such as .DS_Store, aren't the prep's.
        open(os.path.join(self.folder, PREP, ".DS_Store"), "w").close()
        self.assertEqual(check_prep.check_prep(
            PREP, today=TODAY), {"ok": True, "errors": []})

    def test_failures(self):
        # name: (changes to the prep's files, by write_prep()'s arguments,
        # each None when missing, extra file, expected in the errors)
        cases = [("a file more", {}, "notes.md", "move notes.md to your own scratch folder"),
                 ("no request", {"request": None},
                  None, "missing request.json"),
                 ("no identities", {"identities": None},
                  None, "missing identities.json"),
                 ("no orientation", {"orientation": None},
                  None, "missing orientation.json"),
                 ("no feedback", {"feedback": None},
                  None, "missing feedback.json"),
                 ("a request that breaks a rule", {"request": {**REQUEST, "end": "2026-12-31"}}, None,
                  "request.json: the period ends on 31/12/2026"),
                 ("identities that break a rule", {"identities": {**IDENTITIES, "slack-mcp": {}}}, None,
                  "identities.json: slack-mcp must be"),
                 ("an orientation that breaks a rule", {"orientation": {"text": "Strong"}}, None,
                  "orientation.json: the orientation must have the parts"),
                 ("feedback that breaks a rule", {"feedback": {"reviews": [{**REVIEW, "rating": "Good"}]}}, None,
                  "feedback.json: feedback 1's rating, 'Good', must be one of the company's")]
        for i, (name, changes, extra, expected) in enumerate(cases):
            with self.subTest(name):
                prep = f"Case-{i}_26-11-10"
                files = {"request": REQUEST, "identities": IDENTITIES, "orientation": ORIENTATION,
                         "feedback": FEEDBACK, **changes}
                write_prep(self.folder, prep=prep, **files)
                if extra:
                    open(os.path.join(self.folder, prep, extra), "w").close()
                result = check_prep.check_prep(prep, today=TODAY)
                self.assertFalse(result["ok"])
                self.assertIn(expected, " ".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
