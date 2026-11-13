"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/find_person.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

gh is a fake runner and the vault a temporary folder, so nothing reaches a
service and no config but the test's own is read.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import find_person  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, temp_output, write_prep  # noqa: E402


class FakeGh:
    """A gh runner: each search's {login: commits} by its query, and each
    login's profile name; signed in. Records each command."""

    def __init__(self, searches, names):
        self.searches, self.names, self.calls = searches, names, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        args = command[1:]
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "search/commits" in args:
            counts = self.searches.get(
                args[args.index("-f") + 1].removeprefix("q="), {})
            answer = {"items": [{"author": {"login": login}}
                                for login, n in counts.items() for _ in range(n)]}
        else:
            answer = {"name": self.names.get(args[1].removeprefix("users/"))}
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")


class FindPersonTest(unittest.TestCase):
    def test_github_candidates(self):
        # One search, by the email, each account that authored its commits
        # once, with its profile's name, or none.
        run = FakeGh({"author-email:jane@acme.test": {"janedoe": 3, "jdoe-work": 1}},
                     {"janedoe": "Jane Doe"})
        self.assertEqual(find_person.github_candidates("jane@acme.test", run), [
            {"login": "janedoe", "name": "Jane Doe"}, {"login": "jdoe-work", "name": None}])
        self.assertEqual(
            sum("search/commits" in call for call in run.calls), 1)

    def test_vault_candidates(self):
        # Every page and link with a word that starts a word of the name, or
        # that one starts, whatever its case or accents, most mentioned first,
        # with whether it has a page: Jan and Janet count for Jane, but a lone
        # initial and a word holding the name inside it don't. An alias such a
        # page declares counts too, as an alias of it, linked or not; another
        # person's alias doesn't.
        with tempfile.TemporaryDirectory() as graph:
            for folder, name, text in [
                    ("journals", "2026_07_22.md",
                     "- 1:1 with [[Jane]], then #[[Jane Doe]] and [[jane]]"),
                    ("journals", "2026_07_23.md",
                     "- [[Janet]] and [[Meeting with Jane Doe]] #Hiring [[J]] [[Bjane]]"),
                    ("journals", "2026_07_24.md", "- [[Jan]] said"),
                    ("journals", "2026_07_25.md", "- [[JD]] met [[Zed]]"),
                    ("pages", "Jane Doe.md",
                     "alias:: JD, Janie D\n- works with [[Jöhn Doe]]"),
                    ("pages", "Bob Roe.md", "alias:: Zed\n- a colleague"),
                    ("pages", "Recruiting.md", "- #Hiring")]:
                os.makedirs(os.path.join(graph, folder), exist_ok=True)
                with open(os.path.join(graph, folder, name), "w", encoding="utf-8") as f:
                    f.write(text)
            self.assertEqual(find_person.vault_candidates(graph, "Jane Doe"), [
                {"link": "Jane", "mentions": 2, "page": False, "alias_of": None},
                {"link": "Jan", "mentions": 1, "page": False, "alias_of": None},
                {"link": "Jane Doe", "mentions": 1,
                    "page": True, "alias_of": None},
                {"link": "Janet", "mentions": 1, "page": False, "alias_of": None},
                {"link": "JD", "mentions": 1, "page": False, "alias_of": "Jane Doe"},
                {"link": "Jöhn Doe", "mentions": 1,
                    "page": False, "alias_of": None},
                {"link": "Meeting with Jane Doe", "mentions": 1,
                    "page": False, "alias_of": None},
                {"link": "Janie D", "mentions": 0, "page": False, "alias_of": "Jane Doe"}])

    def test_could_name(self):
        # A short form of a word of the name, or a longer form, counts; a
        # lone initial, or the name inside another word, doesn't.
        words = ["alan", "doe"]
        for link, expected in [("Al", True), ("D", False), ("Do", True), ("Meeting with Alan Doe", True),
                               ("Alans", True), ("A", False), ("Balan", False), ("Alarm", False)]:
            with self.subTest(link):
                self.assertEqual(find_person.could_name(link, words), expected)

    def test_find(self):
        # The person as the manager named them, GitHub by the email of the
        # Jira account, the one source step 1 records, and the vault by the
        # name.
        folder = temp_output(self)
        write_prep(folder, person={**PERSON, "sources": {"jira-api": PERSON["sources"]["jira-api"]}},
                   orientation=None, feedback=None)
        run = FakeGh({"author-email:jane@acme.test": {"janedoe": 1}},
                     {"janedoe": "Jane Doe"})
        with tempfile.TemporaryDirectory() as graph, \
                mock.patch.object(common, "gh_available", return_value=True), \
                mock.patch.object(find_person, "graph_path", return_value=graph):
            os.makedirs(os.path.join(graph, "journals"))
            with open(os.path.join(graph, "journals", "2026_09_01.md"), "w", encoding="utf-8") as f:
                f.write("- 1:1 with [[Jane]]")
            found = find_person.find(PREP, run=run)
        self.assertEqual(found, {"person": "Jane Doe", "email": "jane@acme.test",
                                 "github": [{"login": "janedoe", "name": "Jane Doe"}],
                                 "vault": [{"link": "Jane", "mentions": 1, "page": False, "alias_of": None}]})
        with mock.patch.object(common, "gh_available", return_value=False), \
                self.assertRaisesRegex(SystemExit, "github-cli"):
            find_person.find(PREP, run=run)


if __name__ == "__main__":
    unittest.main()
