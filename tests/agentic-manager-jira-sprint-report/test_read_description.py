"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/read_description.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_fixture as fixture  # noqa: E402,F401  (puts the scripts on the path)
import common  # noqa: E402
import read_description  # noqa: E402


class ReadDescriptionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.long = "\n".join(
            f"Line {n} of the description." for n in range(200))
        data = fixture.sprint_data()
        data["spells"][0]["description"] = self.long
        self.pull = next(
            pr for pr in data["other_pull_requests"] if pr["untracked"])
        self.pull["body"] = self.long
        with open(os.path.join(self.tmp.name, common.DATA_FILE), "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.key = data["spells"][0]["key"]
        self.pieces = common.chunks(self.long)

    def read(self, *args):
        out = io.StringIO()
        argv = ["read_description.py", "--report-dir", self.tmp.name, *args]
        with mock.patch("sys.argv", argv), contextlib.redirect_stdout(out):
            read_description.main()
        return out.getvalue()

    def test_a_chunk_is_printed_with_its_place(self):
        self.assertGreater(len(self.pieces), 1)
        for number in (1, len(self.pieces)):
            with self.subTest(number):
                self.assertEqual(
                    self.read("--key", self.key, "--chunk", str(number)),
                    f"{self.key}, chunk {number} of {len(self.pieces)}\n\n{self.pieces[number - 1]}\n")

    def test_an_epic_has_chunks_too(self):
        epic = fixture.sprint_data()["epics"][0]
        self.assertIn(f"{epic['key']}, chunk 1 of 1",
                      self.read("--key", epic["key"]))

    def test_an_untracked_pull_request_has_smaller_chunks(self):
        # Cut as the brief cuts it, by its address.
        pieces = common.chunks(self.long, common.PULL_DESCRIPTION_CHUNK_CHARS)
        self.assertEqual(self.read("--key", self.pull["url"], "--chunk", "2"),
                         f"{self.pull['url']}, chunk 2 of {len(pieces)}\n\n{pieces[1]}\n")

    def test_refusals(self):
        # A pull request on a ticket of the sprint isn't untracked delivery.
        tracked = "https://github.com/acme/api/pull/91"
        cases = [(("--key", "NOPE-1"), "no ticket, epic or untracked pull request NOPE-1"),
                 (("--key", tracked),
                  f"no ticket, epic or untracked pull request {tracked}"),
                 (("--key", self.key, "--chunk", "0"), "--chunk is 1 to"),
                 (("--key", self.key, "--chunk", str(len(self.pieces) + 1)), "--chunk is 1 to")]
        for args, expected in cases:
            with self.subTest(args), self.assertRaisesRegex(SystemExit, expected):
                self.read(*args)


if __name__ == "__main__":
    unittest.main()
