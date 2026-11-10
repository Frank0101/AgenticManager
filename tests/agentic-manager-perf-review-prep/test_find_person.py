"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/find_person.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

Jira is a fake client, gh a fake runner and the vault a temporary folder, so
nothing reaches a service and no config but the test's own is read.
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
import find_person  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, temp_output, write_prep  # noqa: E402

JANE = {"accountId": "a1", "displayName": "Jane Doe",
        "emailAddress": "jane@acme.test", "active": True}
JANET = {"accountId": "a2", "displayName": "Janet Doe",
         "emailAddress": None, "active": True}


class FakeJira:
    """Answers users() from `found`, {query: accounts}, recording each query."""

    def __init__(self, found):
        self.found, self.queries = found, []

    def users(self, query):
        self.queries.append(query)
        return self.found.get(query, [])


class FakeGh:
    """A gh runner: `orgs`, each search's {login: commits} by its query, and
    each login's profile name; signed in. Records each command."""

    def __init__(self, orgs, searches, names):
        self.orgs, self.searches, self.names, self.calls = orgs, searches, names, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        args = command[1:]
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if args[1].startswith("user/orgs"):
            answer = [{"login": org} for org in self.orgs]
        elif "search/commits" in args:
            counts = self.searches.get(
                args[args.index("-f") + 1].removeprefix("q="), {})
            answer = {"items": [{"author": {"login": login}}
                                for login, n in counts.items() for _ in range(n)]}
        else:
            answer = {"name": self.names.get(args[1].removeprefix("users/"))}
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")


class FindPersonTest(unittest.TestCase):
    def test_jira_candidates(self):
        # The full name first; each word of it only when that finds no one,
        # each account once.
        client = FakeJira({"Jane Doe": [JANE]})
        self.assertEqual(find_person.jira_candidates(
            client, "Jane Doe"), [JANE])
        self.assertEqual(client.queries, ["Jane Doe"])
        client = FakeJira({"jane": [JANE], "doe": [JANE, JANET]})
        self.assertEqual(find_person.jira_candidates(
            client, "Jane Doe"), [JANE, JANET])
        self.assertEqual(client.queries, ["Jane Doe", "jane", "doe"])

    def test_github_candidates(self):
        # Each email and the full name, in each of gh's organisations; an
        # account found several ways says so, those found by an email first.
        run = FakeGh(["acme", "beta"],
                     {"author-email:jane@acme.test org:acme": {"janedoe": 3},
                      'author-name:"Jane Doe" org:acme': {"adoe": 1, "janedoe": 2},
                      'author-name:"Jane Doe" org:beta': {"adoe": 1}},
                     {"janedoe": "Jane Doe"})
        self.assertEqual(find_person.github_candidates("Jane Doe", ["jane@acme.test"], run), [
            {"login": "janedoe", "name": "Jane Doe",
             "found_by": ["author-email:jane@acme.test", 'author-name:"Jane Doe"']},
            {"login": "adoe", "name": None, "found_by": ['author-name:"Jane Doe"']}])
        # A quote in the name can't end the search's phrase early.
        run = FakeGh(["acme"], {}, {})
        self.assertEqual(find_person.github_candidates(
            'Jane "JD" Doe', [], run), [])
        self.assertIn('q=author-name:"Jane JD Doe" org:acme', run.calls[1])

    def test_vault_candidates(self):
        # Every page and link with a word that starts a word of the name, or
        # that one starts, whatever its case or accents, most mentioned first,
        # with whether it has a page: Jan and Janet count for Jane, but a lone
        # initial and a word holding the name inside it don't.
        with tempfile.TemporaryDirectory() as graph:
            for folder, name, text in [
                    ("journals", "2026_07_22.md",
                     "- 1:1 with [[Jane]], then #[[Jane Doe]] and [[jane]]"),
                    ("journals", "2026_07_23.md",
                     "- [[Janet]] and [[Meeting with Jane Doe]] #Hiring [[J]] [[Bjane]]"),
                    ("journals", "2026_07_24.md", "- [[Jan]] said"),
                    ("pages", "Jane Doe.md", "- works with [[Jöhn Doe]]"),
                    ("pages", "Recruiting.md", "- #Hiring")]:
                os.makedirs(os.path.join(graph, folder), exist_ok=True)
                with open(os.path.join(graph, folder, name), "w", encoding="utf-8") as f:
                    f.write(text)
            self.assertEqual(find_person.vault_candidates(graph, "Jane Doe"), [
                {"link": "Jane", "mentions": 2, "page": False},
                {"link": "Jan", "mentions": 1, "page": False},
                {"link": "Jane Doe", "mentions": 1, "page": True},
                {"link": "Janet", "mentions": 1, "page": False},
                {"link": "Jöhn Doe", "mentions": 1, "page": False},
                {"link": "Meeting with Jane Doe", "mentions": 1, "page": False}])

    def test_could_name(self):
        # A short form of a word of the name, or a longer form, counts; a
        # lone initial, or the name inside another word, doesn't.
        words = ["alan", "doe"]
        for link, expected in [("Al", True), ("D", False), ("Do", True), ("Meeting with Alan Doe", True),
                               ("Alans", True), ("A", False), ("Balan", False), ("Alarm", False)]:
            with self.subTest(link):
                self.assertEqual(find_person.could_name(link, words), expected)

    def test_find(self):
        # The person from the prep's request, looked up in each source.
        folder = temp_output(self)
        write_prep(folder, identities=None)
        run = FakeGh(["acme"], {"author-email:jane@acme.test org:acme": {"janedoe": 1}},
                     {"janedoe": "Jane Doe"})
        with tempfile.TemporaryDirectory() as graph, \
                mock.patch.object(find_person, "gh_available", return_value=True), \
                mock.patch.object(find_person, "graph_path", return_value=graph):
            found = find_person.find(
                PREP, client=FakeJira({"Jane Doe": [JANE]}), run=run)
        self.assertEqual(found, {"person": "Jane Doe", "jira": [JANE], "vault": [], "github": [
            {"login": "janedoe", "name": "Jane Doe",
             "found_by": ["author-email:jane@acme.test"]}]})
        with mock.patch.object(find_person, "gh_available", return_value=False), \
                self.assertRaisesRegex(SystemExit, "github-cli"):
            find_person.find(PREP, client=FakeJira({}), run=run)

    def test_name_words(self):
        for name, words in [("Jane Doe", ["jane", "doe"]), ("José  Núñez-Ruiz", ["jose", "nunez", "ruiz"]),
                            ("Meeting with Jane Doe", ["meeting", "with", "jane", "doe"]), ("..", [])]:
            with self.subTest(name):
                self.assertEqual(find_person.name_words(name), words)


if __name__ == "__main__":
    unittest.main()
