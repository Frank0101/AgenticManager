"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/common.py.
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
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import IDENTITIES, PREP, REQUEST, temp_output, write_prep  # noqa: E402

TODAY = date(2026, 11, 10)


class CommonTest(unittest.TestCase):
    def test_request_problems(self):
        # name: (changes to the request, or a value instead of it, expected
        # in its problems, or None for none)
        cases = [("valid", {}, None),
                 ("one day", {"start": "2026-11-10"}, None),
                 ("not an object", ["Jane Doe"], "must be a JSON object"),
                 ("a field missing", {"end": None},
                  "fields must be person, start, end"),
                 ("a field more", {
                  "shown": "10/08/2026 to 10/11/2026"}, "fields must be person, start, end"),
                 ("no name", {"person": " "}, "must name the person"),
                 ("a name that isn't text", {
                  "person": 7}, "must name the person"),
                 ("not a date", {"start": "10/08/2026"},
                  "must be a date as YYYY-MM-DD"),
                 ("ends after today", {"end": "2026-12-31"}, "after today"),
                 ("starts after it ends", {"start": "2026-11-10", "end": "2026-08-10"}, "after it ends")]
        for name, change, expected in cases:
            with self.subTest(name):
                request = change if isinstance(change, list) else {
                    k: v for k, v in {**REQUEST, **change}.items() if v is not None}
                problems = common.request_problems(request, TODAY)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_identities_problems(self):
        # name: (changes to the identities, or a value instead of them,
        # expected in their problems, or None for none)
        cases = [("valid", {}, None),
                 ("absent everywhere", {source: {"absent": True}
                  for source in IDENTITIES}, None),
                 ("not an object", ["janedoe"], "must be a JSON object"),
                 ("a source missing", {"slack-mcp": None},
                  "must be those of jira-api"),
                 ("a source more", {
                  "confluence-mcp": {"absent": True}}, "must be those of jira-api"),
                 ("no name", {"github-cli": {"id": "janedoe"}},
                  'github-cli must be {"id": "...", "name": "..."}'),
                 ("a blank id", {"jira-api": {"id": " ",
                  "name": "Jane Doe"}}, "jira-api must be"),
                 ("absent false", {
                  "notion-mcp": {"absent": False}}, "notion-mcp must be"),
                 ("no links", {"logseq-fs": {"links": []}},
                  'logseq-fs must be {"links": ["...", ...]}'),
                 ("a blank link", {
                  "logseq-fs": {"links": ["Jane", " "]}}, "logseq-fs must be"),
                 ("a link twice", {
                  "logseq-fs": {"links": ["Jane", "Jane"]}}, "logseq-fs must be"),
                 ("links that aren't a list", {
                  "logseq-fs": {"links": "Jane"}}, "logseq-fs must be"),
                 ("an id for the vault", {"logseq-fs": {"id": "Jane", "name": "Jane"}}, "logseq-fs must be")]
        for name, change, expected in cases:
            with self.subTest(name):
                identities = change if isinstance(change, list) else {
                    k: v for k, v in {**IDENTITIES, **change}.items() if v is not None}
                problems = common.identities_problems(identities)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_prep_dir(self):
        folder = temp_output(self)
        write_prep(folder)
        self.assertEqual(common.prep_dir(PREP), os.path.join(folder, PREP))
        # name: (prep, expected in the message)
        cases = [("not a prep folder", "Jane-Doe", "not a prep folder"),
                 ("outside the output folder",
                  "../Jane-Doe_26-11-10", "inside the output folder"),
                 ("not there", "John-Doe_26-11-10", "run init_prep.py first")]
        for name, prep, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                common.prep_dir(prep)


if __name__ == "__main__":
    unittest.main()
